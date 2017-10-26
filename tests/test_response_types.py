import asyncio
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


@asyncio.coroutine
def test_stream_response(test_client):

    @asyncio.coroutine
    def stream_response(request):
        session = yield from get_session(request)
        session['will_not'] = 'show up'
        return web.StreamResponse()

    client = yield from test_client(create_app,
                                    ('/stream', stream_response))

    resp = yield from client.get('/stream')
    assert resp.status == 200
    assert SESSION_KEY.upper() not in resp.cookies


@asyncio.coroutine
def test_bad_response_type(test_client):

    @asyncio.coroutine
    def bad_response(request):
        return ''

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        yield from middleware(req, bad_response)


@asyncio.coroutine
def test_prepared_response_type(test_client):

    @asyncio.coroutine
    def prepared_response(request):
        resp = web.Response()
        yield from resp.prepare(request)
        return resp

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request('GET', '/')
    with pytest.raises(RuntimeError):
        yield from middleware(req, prepared_response)
