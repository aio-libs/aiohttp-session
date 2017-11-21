from aiohttp import web
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)


def create_app(loop, *handlers):
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware], loop=loop)
    for url, handler in handlers:
        app.router.add_route('GET', url, handler)
    return app


async def test_exceptions(test_client):

    async def save(request):
        session = await get_session(request)
        session['message'] = 'works'
        raise web.HTTPFound('/show')

    async def show(request):
        session = await get_session(request)
        message = session.get('message')
        return web.Response(text=str(message))

    client = await test_client(create_app, ('/save', save), ('/show', show))

    resp = await client.get('/save')
    assert resp.status == 200
    assert str(resp.url)[-5:] == '/show'
    text = await resp.text()
    assert text == 'works'
