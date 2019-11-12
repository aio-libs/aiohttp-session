from unittest import mock
import json
import time

from aiohttp import web
from aiohttp.web_middlewares import _Handler
from aiohttp.test_utils import TestClient

from typing import Any, Dict

from aiohttp_session import get_session, SimpleCookieStorage
from aiohttp_session import setup as setup_middleware

from typedefs import _TAiohttpClient


def make_cookie(client: TestClient, data: Dict[Any, Any]) -> None:
    session_data = {
        'session': data,
        'created': int(time.time())
    }

    value = json.dumps(session_data)
    # Ignoring type until aiohttp#4252 is released
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': value}  # type: ignore
    )


def create_app(handler: _Handler) -> web.Application:
    app = web.Application()
    setup_middleware(app, SimpleCookieStorage(max_age=10))
    app.router.add_route('GET', '/', handler)
    return app


async def test_max_age_also_returns_expires(
    aiohttp_client: _TAiohttpClient
) -> None:

    async def handler(request: web.Request) -> web.StreamResponse:
        # Ignoring type since time.time is mocked in this context
        time.time.return_value = 0.0  # type: ignore
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    with mock.patch('time.time') as m_clock:
        m_clock.return_value = 0.0

        client = await aiohttp_client(create_app(handler))
        make_cookie(client, {'a': 1, 'b': 2})
        resp = await client.get('/')
        assert resp.status == 200
        assert 'expires=Thu, 01-Jan-1970 00:00:10 GMT' in \
               resp.headers['SET-COOKIE']
