import json
import time
import asyncio

import pytest
import nacl.secret
import nacl.utils
from aiohttp import web
from nacl.encoding import Base64Encoder

from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.nacl_storage import NaClCookieStorage


def test_invalid_key():
    with pytest.raises(ValueError):
        NaClCookieStorage(b'123')  # short key


def make_cookie(client, secretbox, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    cookie_data = json.dumps(session_data).encode('utf-8')
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    data = secretbox.encrypt(cookie_data, nonce,
                             encoder=Base64Encoder).decode('utf-8')

    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': data})


def create_app(handler, key, max_age=None):
    middleware = session_middleware(NaClCookieStorage(key, max_age=max_age))
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


def decrypt(secretbox, cookie_value):
    assert type(cookie_value) == str
    return json.loads(
        secretbox.decrypt(cookie_value.encode('utf-8'),
                          encoder=Base64Encoder).decode('utf-8')
    )


@pytest.fixture
def secretbox(key):
    return nacl.secret.SecretBox(key)


@pytest.fixture
def key():
    return nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)


async def test_create_new_session(aiohttp_client, secretbox, key):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client, secretbox, key):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, secretbox, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_change_session(aiohttp_client, secretbox, key):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, secretbox, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    morsel = resp.cookies['AIOHTTP_SESSION']
    cookie_data = decrypt(secretbox, morsel.value)
    assert 'session' in cookie_data
    assert 'a' in cookie_data['session']
    assert 'b' in cookie_data['session']
    assert 'c' in cookie_data['session']
    assert 'created' in cookie_data
    assert cookie_data['session']['a'] == 1
    assert cookie_data['session']['b'] == 2
    assert cookie_data['session']['c'] == 3
    assert morsel['httponly']
    assert '/' == morsel['path']


async def test_del_cookie_on_session_invalidation(aiohttp_client,
                                                  secretbox, key):

    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, secretbox, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    morsel = resp.cookies['AIOHTTP_SESSION']
    assert '' == morsel.value
    assert not morsel['httponly']
    assert morsel['path'] == '/'


async def test_nacl_session_fixation(aiohttp_client, secretbox, key):
    async def login(request):
        session = await get_session(request)
        session['k'] = 'v'
        return web.Response()

    async def logout(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response()

    app = create_app(login, key)
    app.router.add_route('DELETE', '/', logout)
    client = await aiohttp_client(app)
    resp = await client.get('/')
    assert 'AIOHTTP_SESSION' in resp.cookies
    evil_cookie = resp.cookies['AIOHTTP_SESSION'].value
    resp = await client.delete('/')
    assert resp.cookies['AIOHTTP_SESSION'].value == ""
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': evil_cookie})
    resp = await client.get('/')
    assert resp.cookies['AIOHTTP_SESSION'].value != evil_cookie


async def test_load_session_dont_load_expired_session(aiohttp_client,
                                                      key):
    async def handler(request):
        session = await get_session(request)
        exp_param = request.rel_url.query.get('exp', None)
        if exp_param is None:
            session['a'] = 1
            session['b'] = 2
        else:
            assert {} == session

        return web.Response(body=b'OK')

    client = await aiohttp_client(
        create_app(handler, key, 2)
    )
    resp = await client.get('/')
    assert resp.status == 200

    await asyncio.sleep(5)

    resp = await client.get('/?exp=yes')
    assert resp.status == 200
