import asyncio
import aioredis
import time
from typing import AsyncIterator

from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.redis_storage import RedisStorage


async def handler(request: web.Request) -> web.Response:
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def redis_pool(app: web.Application) -> AsyncIterator[aioredis.commands.Redis]:  # type: ignore[no-any-unimported]
    redis_address = ('127.0.0.1', '6379')
    async with await aioredis.create_redis_pool(redis_address, timeout=1) as redis:
        storage = RedisStorage(redis)
        setup(app, storage)
        yield


def make_app() -> web.Application:
    app = web.Application()
    app.cleanup_ctx.append(redis_pool)
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
