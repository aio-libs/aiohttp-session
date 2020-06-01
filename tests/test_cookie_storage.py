import json
import re
import time

from aiohttp import web
from aiohttp_session import (Session, session_middleware,
                             get_session, SimpleCookieStorage,
                             _cookie_unsafe_char, _to_cookiesafe_json,
                             _from_cookiesafe_json)


def make_cookie(client, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    value = _to_cookiesafe_json(session_data)
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': value})


def create_app(handler):
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


async def test_create_new_session(aiohttp_client):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler))
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert session.created is not None
        assert {'a': 1, 'b': 2} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200


async def test_change_session(aiohttp_client):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    morsel = resp.cookies['AIOHTTP_SESSION']
    cookie_data = _from_cookiesafe_json(morsel.value)
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


async def test_clear_cookie_on_session_invalidation(aiohttp_client):

    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200
    assert ('Set-Cookie: AIOHTTP_SESSION="{}"; '
            'domain=127.0.0.1; httponly; Path=/'.upper()) == \
        resp.cookies['AIOHTTP_SESSION'].output().upper()


async def test_dont_save_not_requested_session(aiohttp_client):

    async def handler(request):
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200
    assert 'AIOHTTP_SESSION' not in resp.cookies

async def test_cookie_has_valid_grammar(aiohttp_client):
    async def handler(request):
        session = await get_session(request)
        session['key'] = 'funky" value'
        return web.Response(body=b'OK')
    client = await aiohttp_client(create_app(handler))
    resp = await client.get('/')
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert set(_cookie_unsafe_char.findall(morsel.value)) == {'%'}

def test_cookiesafe_json():
    bad_chars = {' ', '\t', '\n', '"', ',', ';', '\\', '\x00', '\U0001f4a9'}
    bad_strings = bad_chars | {'buffer_' + c + '_buffer' for c in bad_chars}
    safe_strings = {'fine', 'punctuation-_{}<>()!'}

    for string in bad_strings | safe_strings:
        encoded = _to_cookiesafe_json(string)
        assert string == _from_cookiesafe_json(encoded)
        assert not set(encoded).intersection(bad_chars)

    for safe_string in safe_strings:
        assert safe_string in _to_cookiesafe_json(safe_string)[3:-3]
