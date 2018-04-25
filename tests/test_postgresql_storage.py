import pytest
import uuid
import time
import re
import asyncio

from datetime import datetime
from aiohttp import web
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.postgresql_storage import PostgresqlAbstractStorage, \
                                               PostgresqlAsyncpgStorage, \
                                               PostgresqlAiopgStorage


class NotImplementedStorage(PostgresqlAbstractStorage):
    pass


def table_name(PGStorage, data_type):
    return 'session_{}_{}'.format(PGStorage.__name__.lower(), data_type)


def psql_cases(asyncpg_pool, aiopg_pool):
    for pgpool, PGStorage in [(asyncpg_pool, PostgresqlAsyncpgStorage),
                              (aiopg_pool, PostgresqlAiopgStorage)]:
        for data_type in ('text', 'jsonb'):
            yield pgpool, PGStorage, data_type


async def create_app(handler, pgpool, PGStorage, data_type, max_age=None,
                     key_factory=lambda: uuid.uuid4().hex,
                     delete_expired_every=3600):
    storage = PGStorage(pgpool, table_name=table_name(PGStorage, data_type),
                        max_age=max_age, key_factory=key_factory,
                        data_type=data_type)
    await storage.initialize(delete_expired_every=delete_expired_every)
    middleware = session_middleware(storage)
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app, storage


async def make_cookie(client, storage, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }
    key = uuid.uuid4().hex
    value = storage._encoder(session_data)
    await storage._execute_query(storage._query_save_session,
                                 *(key, value, None))
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def make_cookie_with_bad_value(client, storage):
    key = uuid.uuid4().hex
    await storage._execute_query(storage._query_save_session,
                                 *(key, '', None))
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def load_cookie(client, storage):
    cookies = client.session.cookie_jar.filter_cookies(client.make_url('/'))
    key = cookies['AIOHTTP_SESSION']
    result = await storage._execute_query(storage._query_load_session,
                                          *(key.value, datetime.utcnow()),
                                          fetchrow=True)
    return storage._decoder(result[0])


def query_expire(storage):
    return re.sub(' {} '.format(storage._column_name_data),
                  ' {} '.format(storage._column_name_expire),
                  storage._query_load_session)


def query_session_key_absolutely(storage, key):
    return '''SELECT {data} FROM {schema_name}.{table_name} WHERE
                {key} = '{key_value}'
           '''.format(
                schema_name=storage._schema_name,
                table_name=storage._table_name,
                data=storage._column_name_data,
                key=storage._column_name_key,
                key_value=key)


async def test_create_new_session(aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200
        storage.finalize()


async def test_load_existing_session(aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        await make_cookie(client, storage, {'a': 1, 'b': 12})
        resp = await client.get('/')
        assert resp.status == 200
        storage.finalize()


async def test_load_non_existent_session(
        aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        client.session.cookie_jar.update_cookies(
            {'AIOHTTP_SESSION': 'non_existent_key'})
        resp = await client.get('/')
        assert resp.status == 200
        storage.finalize()


async def test_load_bad_session(aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        # cannot store bad format in jsonb storage
        if data_type != 'jsonb':
            app, storage = await create_app(handler, pgpool, PGStorage,
                                            data_type)
            client = await aiohttp_client(app)
            await make_cookie_with_bad_value(client, storage)
            resp = await client.get('/')
            assert resp.status == 200
            storage.finalize()


async def test_change_session(aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        await make_cookie(client, storage, {'a': 1, 'b': 2})
        resp = await client.get('/')
        assert resp.status == 200
        value = await load_cookie(client, storage)
        assert 'session' in value
        assert 'a' in value['session']
        assert 'b' in value['session']
        assert 'c' in value['session']
        assert 'created' in value
        assert value['session']['a'] == 1
        assert value['session']['b'] == 2
        assert value['session']['c'] == 3
        morsel = resp.cookies['AIOHTTP_SESSION']
        assert morsel['httponly']
        assert '/' == morsel['path']
        storage.finalize()


async def test_clear_cookie_on_session_invalidation(aiohttp_client,
                                                    asyncpg_pool, aiopg_pool):
    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        await make_cookie(client, storage, {'a': 1, 'b': 2})
        resp = await client.get('/')
        assert resp.status == 200

        value = await load_cookie(client, storage)
        assert {} == value
        morsel = resp.cookies['AIOHTTP_SESSION']
        assert morsel['path'] == '/'
        assert morsel['expires'] == "Thu, 01 Jan 1970 00:00:00 GMT"
        assert morsel['max-age'] == "0"
        storage.finalize()


async def test_create_cookie_in_handler(aiohttp_client,
                                        asyncpg_pool, aiopg_pool):
    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        session['b'] = 2
        return web.Response(body=b'OK', headers={'HOST': 'example.com'})

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200

        value = await load_cookie(client, storage)
        assert 'session' in value
        assert 'a' in value['session']
        assert 'b' in value['session']
        assert 'created' in value
        assert value['session']['a'] == 1
        assert value['session']['b'] == 2
        morsel = resp.cookies['AIOHTTP_SESSION']
        assert morsel['httponly']
        assert morsel['path'] == '/'
        result = await storage._execute_query(
            storage._query_load_session,
            *(morsel.value, datetime.utcnow()),
            fetchrow=True)
        assert result
        storage.finalize()


async def test_set_ttl_on_session_saving(aiohttp_client,
                                         asyncpg_pool, aiopg_pool):
    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type,
                                        max_age=10)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200

        key = resp.cookies['AIOHTTP_SESSION'].value
        result = await storage._execute_query(query_expire(storage),
                                              *(key, datetime.utcnow()),
                                              fetchrow=True)
        ttl = (result[0] - datetime.utcnow()).total_seconds()

        assert ttl > 9
        assert ttl <= 10
        storage.finalize()


async def test_set_ttl_manually_set(aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        session.max_age = 10
        session['a'] = 1
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200

        key = resp.cookies['AIOHTTP_SESSION'].value
        result = await storage._execute_query(query_expire(storage),
                                              *(key, datetime.utcnow()),
                                              fetchrow=True)
        ttl = (result[0] - datetime.utcnow()).total_seconds()

        assert ttl > 9
        assert ttl <= 10
        storage.finalize()


async def test_create_new_session_if_key_doesnt_exists_in_postgres(
        aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        assert session.new
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200
        client.session.cookie_jar.update_cookies(
            {'AIOHTTP_SESSION': 'invalid_key'})
        storage.finalize()


async def test_create_storate_with_custom_key_factory(
        aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        session['key'] = 'value'
        assert session.new
        return web.Response(body=b'OK')

    def key_factory():
        return 'test-key'

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type,
                                        key_factory=key_factory)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200

        assert resp.cookies['AIOHTTP_SESSION'].value == 'test-key'

        value = await load_cookie(client, storage)
        assert 'key' in value['session']
        assert value['session']['key'] == 'value'
        storage.finalize()


async def test_postgresql_not_fetch_exipred_session(aiohttp_client,
                                                    asyncpg_pool, aiopg_pool):
    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type,
                                        max_age=1)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200
        key = resp.cookies['AIOHTTP_SESSION'].value

        result = await storage._execute_query(
            storage._query_load_session,
            *(key, datetime.utcnow()),
            fetchrow=True)
        assert result

        await asyncio.sleep(2)

        result = await storage._execute_query(
            storage._query_load_session,
            *(key, datetime.utcnow()),
            fetchrow=True)
        assert not result
        storage.finalize()


async def test_postgresql_remove_exipred_row(aiohttp_client,
                                             asyncpg_pool, aiopg_pool):
    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        app, storage = await create_app(handler, pgpool, PGStorage, data_type,
                                        max_age=1, delete_expired_every=1)
        client = await aiohttp_client(app)
        resp = await client.get('/')
        assert resp.status == 200
        key = resp.cookies['AIOHTTP_SESSION'].value

        result = await storage._execute_query(
            storage._query_load_session,
            *(key, datetime.utcnow()),
            fetchrow=True)
        assert result

        await asyncio.sleep(2)

        result = await storage._execute_query(
            query_session_key_absolutely(storage, key),
            fetchrow=True)
        assert not result
        storage.finalize()


async def test_postgresql_jsonb_session_storage(
        aiohttp_client, asyncpg_pool, aiopg_pool):

    async def handler(request):
        session = await get_session(request)
        session['a'] = 123
        return web.Response(body=b'OK')

    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        if data_type == 'jsonb':
            app, storage = await create_app(
                handler, pgpool, PGStorage, data_type)
            client = await aiohttp_client(app)
            await make_cookie(client, storage, {'a': 1})
            resp = await client.get('/')
            assert resp.status == 200
            async with asyncpg_pool.acquire() as conn:
                val = await conn.fetchval('''
                    SELECT data->'session'->$1 FROM {table}
                        WHERE key = $2;'''.format(
                            table=table_name(PGStorage, data_type)),
                    *('a', list(client.session.cookie_jar)[0].value))
            assert val == 123
            storage.finalize()


async def test_asyncpg_pool_not_provided_to_storage():
    with pytest.raises(TypeError):
        PostgresqlAsyncpgStorage(None)


async def test_aiopg_pool_not_provided_to_storage():
    with pytest.raises(TypeError):
        PostgresqlAiopgStorage(None)


async def test_no_asyncpg_installed(mocker):
    mocker.patch('aiohttp_session.postgresql_storage.asyncpg', None)
    with pytest.raises(RuntimeError):
        PostgresqlAsyncpgStorage(None)


async def test_no_aiopg_installed(mocker):
    mocker.patch('aiohttp_session.postgresql_storage.aiopg', None)
    with pytest.raises(RuntimeError):
        PostgresqlAiopgStorage(None)


async def test_invalid_sql_names():
    for Storage in (PostgresqlAsyncpgStorage, PostgresqlAiopgStorage):
        with pytest.raises(ValueError):
            Storage(None, schema_name='6a-b')
        with pytest.raises(ValueError):
            Storage(None, table_name='6a-b')
        with pytest.raises(ValueError):
            Storage(None, column_name_key='6a-b')
        with pytest.raises(ValueError):
            Storage(None, column_name_data='6a-b')
        with pytest.raises(ValueError):
            Storage(None, column_name_expire='6a-b')
        with pytest.raises(ValueError):
            Storage(None, data_type='yaml')


async def test_class_inheritance_not_implemented():
    with pytest.raises(NotImplementedError):
        storage = NotImplementedStorage(None)
        await storage._execute_query(
            query_session_key_absolutely(storage, 'abc'))


async def test_initialize_with_non_default_parameters(
        asyncpg_pool, aiopg_pool):
    for pgpool, PGStorage, data_type in psql_cases(asyncpg_pool, aiopg_pool):
        storage = PGStorage(pgpool,
                            table_name=table_name(PGStorage, data_type),
                            data_type=data_type)
        await storage.initialize(setup_table=False, delete_expired_every=0)
        storage.finalize()
