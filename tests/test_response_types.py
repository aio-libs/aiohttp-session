import pytest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_middlewares import _Handler

from typing import no_type_check, Tuple

from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage, SESSION_KEY)

from typedefs import _TAiohttpClient


def create_app(*handlers: Tuple[str, _Handler]) -> web.Application:
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


async def test_stream_response(aiohttp_client: _TAiohttpClient) -> None:

    async def stream_response(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session['will_not'] = 'show up'
        return web.StreamResponse()

    client = await aiohttp_client(create_app(('/stream', stream_response)))

    resp = await client.get('/stream')
    assert resp.status == 200
    assert SESSION_KEY.upper() not in resp.cookies


async def test_bad_response_type(aiohttp_client: _TAiohttpClient) -> None:

    # Ignoring typing since return type is on purpose wrong
    @no_type_check
    async def bad_response(request: web.Request) -> str:
        return ''

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        await middleware(req, bad_response)


async def test_prepared_response_type(
    aiohttp_client: _TAiohttpClient
) -> None:

    async def prepared_response(request: web.Request) -> web.StreamResponse:
        resp = web.Response()
        await resp.prepare(request)
        return resp

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        await middleware(req, prepared_response)
