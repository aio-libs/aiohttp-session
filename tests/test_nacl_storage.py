import json
import time
import asyncio

import pytest
import nacl.secret
import nacl.utils
from aiohttp import web
from aiohttp.web_middlewares import _Handler
from aiohttp.test_utils import TestClient

from nacl.encoding import Base64Encoder

from typing import no_type_check, Any, Dict, Optional

from aiohttp_session import (Session, session_middleware, get_session,
                             new_session)
from aiohttp_session.nacl_storage import NaClCookieStorage

from typedefs import _TAiohttpClient


def test_invalid_key() -> None:
    with pytest.raises(ValueError):
        NaClCookieStorage(b'123')  # short key


def make_cookie(
    client: TestClient,
    secretbox: nacl.secret.SecretBox,
    data: Dict[Any, Any]
) -> None:
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    cookie_data = json.dumps(session_data).encode('utf-8')
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    data = secretbox.encrypt(cookie_data, nonce,
                             encoder=Base64Encoder).decode('utf-8')

    # Ignoring type until aiohttp#4252 is released
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': data}  # type: ignore
    )


def create_app(
    handler: _Handler,
    key: bytes,
    max_age: Optional[int] = None
) -> web.Application:
    middleware = session_middleware(NaClCookieStorage(key, max_age=max_age))
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


def decrypt(secretbox: nacl.secret.SecretBox, cookie_value: str) -> Any:
    assert type(cookie_value) == str
    return json.loads(
        secretbox.decrypt(cookie_value.encode('utf-8'),
                          encoder=Base64Encoder).decode('utf-8')
    )


# pytest.fixture decorator strips the typing of the decorated function
@no_type_check
@pytest.fixture
def secretbox(key: bytes) -> nacl.secret.SecretBox:
    return nacl.secret.SecretBox(key)


# pytest.fixture decorator strips the typing of the decorated function
@no_type_check
@pytest.fixture
def key() -> bytes:
    return nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)


async def test_create_new_session(
    aiohttp_client: _TAiohttpClient,
    secretbox: nacl.secret.SecretBox,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(
    aiohttp_client: _TAiohttpClient,
    secretbox: nacl.secret.SecretBox,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
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


async def test_change_session(
    aiohttp_client: _TAiohttpClient,
    secretbox: nacl.secret.SecretBox,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
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


async def test_del_cookie_on_session_invalidation(
    aiohttp_client: _TAiohttpClient,
    secretbox: nacl.secret.SecretBox,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
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


async def test_nacl_session_fixation(
    aiohttp_client: _TAiohttpClient,
    secretbox: nacl.secret.SecretBox,
    key: bytes
) -> None:

    async def login(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session['k'] = 'v'
        return web.Response()

    async def logout(request: web.Request) -> web.StreamResponse:
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
    # Ignoring type until aiohttp#4252 is released
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': evil_cookie}  # type: ignore
    )
    resp = await client.get('/')
    assert resp.cookies['AIOHTTP_SESSION'].value != evil_cookie


async def test_load_session_dont_load_expired_session(
    aiohttp_client: _TAiohttpClient,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
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


async def test_load_corrupted_session(
    aiohttp_client: _TAiohttpClient,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    # Ignoring type until aiohttp#4252 is released
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': 'bad key'}  # type: ignore
    )
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_session_different_key(
    aiohttp_client: _TAiohttpClient,
    key: bytes
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, key))
    # create another box with another key
    key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
    secretbox = nacl.secret.SecretBox(key)
    make_cookie(client, secretbox, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_expired_session(
    aiohttp_client: _TAiohttpClient,
    key: bytes
) -> None:
    MAX_AGE = 2

    async def login(request: web.Request) -> web.StreamResponse:
        session = await new_session(request)
        session['created'] = int(time.time())
        return web.Response()

    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        created = session.get('created', None) if not session.new else None
        text = ''
        if created is not None and (time.time() - created) > MAX_AGE:
            text += 'WARNING!'
        return web.Response(text=text)

    app = create_app(handler, key, max_age=MAX_AGE)
    app.router.add_route('POST', '/', login)

    client = await aiohttp_client(app)
    resp = await client.post('/')
    assert 'AIOHTTP_SESSION' in resp.cookies
    cookie = resp.cookies['AIOHTTP_SESSION'].value
    await asyncio.sleep(MAX_AGE + 1)
    # Ignoring type until aiohttp#4252 is released
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': cookie}  # type: ignore
    )
    resp = await client.get('/')
    body = await resp.text()
    assert body == ''
