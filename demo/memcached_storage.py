import asyncio
import time

import aiomcache
from aiohttp import web
from aiohttp_session import get_session, setup
from aiohttp_session.memcached_storage import MemcachedStorage


async def handler(request: web.Request) -> web.Response:
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def make_app() -> web.Application:
    app = web.Application()
    mc = aiomcache.Client("127.0.0.1", 11211, loop=loop)
    setup(app, MemcachedStorage(mc))
    app.router.add_get('/', handler)
    return app

loop = asyncio.get_event_loop()
app = loop.run_until_complete(make_app())
web.run_app(app)
