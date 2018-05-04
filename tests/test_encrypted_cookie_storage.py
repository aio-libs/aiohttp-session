import json
import base64
import time

import pytest
from aiohttp import web

from cryptography.fernet import Fernet

from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


def make_cookie(client, fernet, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    cookie_data = json.dumps(session_data).encode('utf-8')
    data = fernet.encrypt(cookie_data).decode('utf-8')

    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': data})


def create_app(handler, key):
    middleware = session_middleware(EncryptedCookieStorage(key))
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


def decrypt(fernet, cookie_value):
    assert type(cookie_value) == str
    return json.loads(
        fernet.decrypt(cookie_value.encode('utf-8')).decode('utf-8')
    )


@pytest.fixture
def fernet_and_key():
    key = Fernet.generate_key()
    fernet = Fernet(key)
    return fernet, base64.urlsafe_b64decode(key)


@pytest.fixture
def fernet(fernet_and_key):
    return fernet_and_key[0]


@pytest.fixture
def key(fernet_and_key):
    return fernet_and_key[1]


def test_invalid_key():
    with pytest.raises(ValueError):
        EncryptedCookieStorage(b'123')  # short key


async def test_create_new_session_broken_by_format(aiohttp_client,
                                                   fernet, key):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    new_fernet = Fernet(Fernet.generate_key())
    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, new_fernet, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client, fernet, key):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, fernet, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_change_session(aiohttp_client, fernet, key):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, fernet, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    morsel = resp.cookies['AIOHTTP_SESSION']
    cookie_data = decrypt(fernet, morsel.value)
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


async def test_clear_cookie_on_session_invalidation(aiohttp_client,
                                                    fernet, key):

    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    make_cookie(client, fernet, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    morsel = resp.cookies['AIOHTTP_SESSION']
    assert '' == morsel.value
    assert not morsel['httponly']
    assert morsel['path'] == '/'


async def test_encrypted_cookie_session_fixation(aiohttp_client, fernet, key):
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
