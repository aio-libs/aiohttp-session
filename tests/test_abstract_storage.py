from unittest import mock
import json
import time

from aiohttp import web
from aiohttp_session import get_session, SimpleCookieStorage
from aiohttp_session import setup as setup_middleware


def make_cookie(client, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    value = json.dumps(session_data)
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': value})


def create_app(loop, handler):
    app = web.Application(loop=loop)
    setup_middleware(app, SimpleCookieStorage(max_age=10))
    app.router.add_route('GET', '/', handler)
    return app


async def test_max_age_also_returns_expires(test_client):

    async def handler(request):
        time.time.return_value = 0.0
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    with mock.patch('time.time') as m_clock:
        m_clock.return_value = 0.0

        client = await test_client(create_app, handler)
        make_cookie(client, {'a': 1, 'b': 2})
        resp = await client.get('/')
        assert resp.status == 200
        assert 'expires=Thu, 01-Jan-1970 00:00:10 GMT' in \
               resp.headers['SET-COOKIE']
