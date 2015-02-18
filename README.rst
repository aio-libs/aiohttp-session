# aiohttp_session
Provide sessions for aiohttp.web

Usage::

    import asycio
    import time
    from aiohttp import web
    import aiohttp_session

    @asyncio.coroutine
    def handler(request):
        session = aiohttp_session.get_session(request)
        session['last_visit'] = time.time()
        return web.Response('OK')

    app = web.Application(middlewares=aiohttp_session.session_middleware(
        aiohttp_session.EncryptedCookieStorage('secret')))

    app.router.add_route('GET', '/', handler)

