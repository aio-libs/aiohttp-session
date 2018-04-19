import asyncio
import asyncpg
import time

from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.postgresql_storage import PostgresqlAsyncpgStorage


POSTGRES_DSN = 'postgresql://user:pass@host/dbname'


async def handler(request):
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def make_pool_storage():
    pool = await asyncpg.create_pool(POSTGRES_DSN)
    storage = PostgresqlAsyncpgStorage(pool)
    await storage.initialize()
    return pool, storage


def make_app():
    loop = asyncio.get_event_loop()
    pool, storage = loop.run_until_complete(make_pool_storage())

    async def dispose_postgresql(app):
        storage.finalize()
        await pool.close()

    app = web.Application()
    setup(app, storage)
    app.on_cleanup.append(dispose_postgresql)
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
