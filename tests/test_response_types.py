import pytest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage, SESSION_KEY)


def create_app(loop, *handlers):
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware], loop=loop)
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


async def test_stream_response(test_client):

    async def stream_response(request):
        session = await get_session(request)
        session['will_not'] = 'show up'
        return web.StreamResponse()

    client = await test_client(create_app, ('/stream', stream_response))

    resp = await client.get('/stream')
    assert resp.status == 200
    assert SESSION_KEY.upper() not in resp.cookies


async def test_bad_response_type(test_client):

    async def bad_response(request):
        return ''

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        await middleware(req, bad_response)


async def test_prepared_response_type(test_client):

    async def prepared_response(request):
        resp = web.Response()
        await resp.prepare(request)
        return resp

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        await middleware(req, prepared_response)
