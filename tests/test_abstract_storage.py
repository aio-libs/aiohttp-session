import asyncio
from unittest import mock
import json
import time

from aiohttp import web
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)


def make_cookie(client, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    value = json.dumps(session_data)
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': value})


def create_app(loop, handler):
    middleware = session_middleware(SimpleCookieStorage(max_age=10))
    app = web.Application(middlewares=[middleware], loop=loop)
    app.router.add_route('GET', '/', handler)
    return app


@asyncio.coroutine
def test_max_age_also_returns_expires(test_client):

    @asyncio.coroutine
    def handler(request):
        time.monotonic.return_value = 0.0
        session = yield from get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    with mock.patch('time.monotonic') as m_monotonic:
        m_monotonic.return_value = 0.0

        client = yield from test_client(create_app, handler)
        make_cookie(client, {'a': 1, 'b': 2})
        resp = yield from client.get('/')
        assert resp.status == 200
        assert 'expires=Thu, 01-Jan-1970 00:00:10 GMT' in \
               resp.headers['SET-COOKIE']
