import asyncio
import aiopg
import time

from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.postgresql_storage import PostgresqlAiopgStorage

#
# before running this example, set up valid DSN
# for access your Postgresql database
#
POSTGRES_DSN = 'postgresql://user:pass@host:port/dbname'


async def handler(request):
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


async def make_pool_storage():
    pool = await aiopg.create_pool(POSTGRES_DSN)
    storage = PostgresqlAiopgStorage(pool)
    await storage.initialize()
    return pool, storage


def make_app():
    loop = asyncio.get_event_loop()
    pool, storage = loop.run_until_complete(make_pool_storage())

    async def dispose_postgresql(app):
        storage.finalize()
        pool.close()
        await pool.wait_closed()

    app = web.Application()
    setup(app, storage)
    app.on_cleanup.append(dispose_postgresql)
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
