import aioredis
import time

from aiohttp import web
from aiohttp_session import get_session, setup
from aiohttp_session.redis_storage import RedisStorage


async def handler(request):
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def create_redis(app):
    redis_address = ('127.0.0.1', '6379')
    app["redis"] = await aioredis.create_redis_pool(redis_address, timeout=1)


async def dispose_redis(app):
    app["redis"].close()
    await app["redis"].wait_closed()


async def setup_aiohttp_session(app):
    storage = RedisStorage(app["redis"])
    setup(app, storage)


def make_app():
    app = web.Application()
    app.on_startup.append(create_redis)
    app.on_startup.append(setup_aiohttp_session)
    app.on_cleanup.append(dispose_redis)
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
