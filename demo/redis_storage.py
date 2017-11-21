import asyncio
import aioredis
import time

from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.redis_storage import RedisStorage


async def handler(request):
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def make_redis_pool():
    redis_address = ('127.0.0.1', '6379')
    return await aioredis.create_redis_pool(redis_address, timeout=1)


def make_app():
    loop = asyncio.get_event_loop()
    redis_pool = loop.run_until_complete(make_redis_pool())
    storage = RedisStorage(redis_pool)

    async def dispose_redis_pool(app):
        redis_pool.close()
        await redis_pool.wait_closed()

    app = web.Application()
    setup(app, storage)
    app.on_cleanup.append(dispose_redis_pool)
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
