from aiohttp import web
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)


def create_app(*handlers):
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


async def test_exceptions(aiohttp_client):

    async def save(request):
        session = await get_session(request)
        session['message'] = 'works'
        raise web.HTTPFound('/show')

    async def show(request):
        session = await get_session(request)
        message = session.get('message')
        return web.Response(text=str(message))

    client = await aiohttp_client(create_app(('/save', save), ('/show', show)))

    resp = await client.get('/save')
    assert resp.status == 200
    assert str(resp.url)[-5:] == '/show'
    text = await resp.text()
    assert text == 'works'
