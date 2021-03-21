from aiohttp import web
from aiohttp.web_middlewares import _Handler

from typing import Tuple

from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)

from typedefs import _TAiohttpClient


def create_app(*handlers: Tuple[str, _Handler]) -> web.Application:
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


async def test_exceptions(aiohttp_client: _TAiohttpClient) -> None:

    async def save(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session['message'] = 'works'
        raise web.HTTPFound('/show')

    async def show(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        message = session.get('message')
        return web.Response(text=str(message))

    client = await aiohttp_client(create_app(('/save', save), ('/show', show)))

    resp = await client.get('/save')
    assert resp.status == 200
    assert str(resp.url)[-5:] == '/show'
    text = await resp.text()
    assert text == 'works'
