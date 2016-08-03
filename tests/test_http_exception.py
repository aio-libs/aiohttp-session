import asyncio

from aiohttp import web
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)


def create_app(loop, *handlers):
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware], loop=loop)
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


@asyncio.coroutine
def test_exceptions(test_client):

    @asyncio.coroutine
    def save(request):
        session = yield from get_session(request)
        session['message'] = 'works'
        raise web.HTTPFound('/show')

    @asyncio.coroutine
    def show(request):
        session = yield from get_session(request)
        message = session.get('message')
        return web.Response(text=str(message))

    client = yield from test_client(create_app,
                                    ('/save', save),
                                    ('/show', show))

    resp = yield from client.get('/save')
    assert resp.status == 200
    assert resp.url[-5:] == '/show'
    text = yield from resp.text()
    assert text == 'works'
