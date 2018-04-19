try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None
try:
    import aiopg
except ImportError:  # pragma: no cover
    aiopg = None

import re
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from . import AbstractStorage, Session


RE_PG_IDENTIFIERS = re.compile('[^\W\d][\w$]{0,62}')
RE_QUERY_PARAMS = re.compile(' \$\d ')


class PostgresqlAbstractStorage(AbstractStorage):
    """Postgresql abstract storage"""

    def __init__(self, driver_pool, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 key_factory=lambda: uuid.uuid4().hex,
                 encoder=json.dumps, decoder=json.loads,
                 schema_name='public', table_name='aiohttp_session',
                 column_name_key='key', column_name_data='data',
                 column_name_expire='expire', data_type='text',
                 timeout=None):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        self._key_factory = key_factory
        self._driver_pool = driver_pool
        self._timeout = timeout
        self._task_delete_exired = None

        self._schema_name = str(schema_name)
        if not RE_PG_IDENTIFIERS.fullmatch(self._schema_name):
            raise ValueError('Schema name "{}" is invalid Postgresql name'
                             .format(schema_name))
        self._table_name = str(table_name)
        if not RE_PG_IDENTIFIERS.fullmatch(self._table_name):
            raise ValueError('Table name "{}" is invalid Postgresql name'
                             .format(table_name))
        self._column_name_key = str(column_name_key)
        if not RE_PG_IDENTIFIERS.fullmatch(self._column_name_key):
            raise ValueError('Column name "{}" is invalid Postgresql name'
                             .format(column_name_key))
        self._column_name_data = str(column_name_data)
        if not RE_PG_IDENTIFIERS.fullmatch(self._column_name_data):
            raise ValueError('Column name "{}" is invalid Postgresql name'
                             .format(column_name_data))
        self._column_name_expire = str(column_name_expire)
        if not RE_PG_IDENTIFIERS.fullmatch(self._column_name_expire):
            raise ValueError('Column name "{}" is invalid Postgresql name'
                             .format(column_name_expire))
        if data_type not in ('jsonb', 'text'):
            raise ValueError('Data type must be one of values: '
                             '"text", "jsonb", got {}'
                             .format(data_type))
        self._data_type = data_type
        self._prepare_queries()

    def _prepare_queries(self):
        self._query_setup_table_if_not_exists = '''
            CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} (
                {key}       varchar(128) PRIMARY KEY NOT NULL,
                {data}      {data_type} DEFAULT '{{}}' NOT NULL,
                {expire}    timestamp without time zone
            );
            CREATE INDEX IF NOT EXISTS {table_name}_{expire}
                ON {table_name} ({expire});
            '''.format(
                    schema_name=self._schema_name,
                    table_name=self._table_name,
                    key=self._column_name_key,
                    data=self._column_name_data,
                    data_type=self._data_type.upper(),
                    expire=self._column_name_expire,
            )
        self._query_delete_expired_sessions = '''
            DELETE FROM {schema_name}.{table_name} WHERE {expire} <= $1 ;
             '''.format(
                    schema_name=self._schema_name,
                    table_name=self._table_name,
                    expire=self._column_name_expire,
            )
        self._query_load_session = '''
            SELECT {data} FROM {schema_name}.{table_name} WHERE
                {key} = $1 AND
                ({expire} > $2 OR {expire} IS NULL);
            '''.format(
                    schema_name=self._schema_name,
                    table_name=self._table_name,
                    key=self._column_name_key,
                    data=self._column_name_data,
                    expire=self._column_name_expire,
           )
        self._query_save_session = '''
            INSERT INTO {schema_name}.{table_name}({key}, {data}, {expire})
                VALUES ( $1 , $2 , $3 )
                ON CONFLICT ({key}) DO UPDATE SET
                    {data}=EXCLUDED.{data},
                    {expire}=EXCLUDED.{expire};
            '''.format(
                    schema_name=self._schema_name,
                    table_name=self._table_name,
                    key=self._column_name_key,
                    data=self._column_name_data,
                    expire=self._column_name_expire,
            )

    async def _execute_query(self, query, *params):
        raise NotImplementedError('Storage for specific driver '
                                  'must implement this method')

    async def _delete_expired_sessions(self):
        await self._execute_query(self._query_delete_expired_sessions,
                                  *(datetime.utcnow(),))
        await asyncio.sleep(self._delete_expired_every)
        self._task_delete_expired = asyncio.ensure_future(
            self._delete_expired_sessions())

    async def initialize(self, setup_table=True, delete_expired_every=3600):
        if setup_table:
            await self._execute_query(self._query_setup_table_if_not_exists)
        if delete_expired_every:
            self._delete_expired_every = delete_expired_every
            self._task_delete_expired = asyncio.ensure_future(
                self._delete_expired_sessions())

    def finalize(self):
        if hasattr(self, '_task_delete_expired'):
            self._task_delete_expired.cancel()

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            key = str(cookie)
            result = await self._execute_query(self._query_load_session,
                                               *(key, datetime.utcnow()),
                                               fetchrow=True)
            if result is None:
                return Session(None, data=None, new=True, max_age=self.max_age)
            else:
                data = result[0]
                try:
                    data = self._decoder(data)
                except ValueError:
                    data = None
                return Session(key, data=data, new=False, max_age=self.max_age)

    async def save_session(self, request, response, session):
        key = session.identity
        if key is None:
            key = self._key_factory()
            self.save_cookie(response, key,
                             max_age=session.max_age)
        else:
            if session.empty:
                self.save_cookie(response, '',
                                 max_age=session.max_age)
            else:
                key = str(key)
                self.save_cookie(response, key,
                                 max_age=session.max_age)

        data = self._encoder(self._get_session_data(session))
        expire = datetime.utcnow() + timedelta(seconds=session.max_age) \
            if session.max_age is not None else None
        await self._execute_query(self._query_save_session,
                                  *(key, data, expire))


class PostgresqlAsyncpgStorage(PostgresqlAbstractStorage):
    """Postgresql asyncpg storage"""

    def __init__(self, asyncpg_pool, *args, **kwargs):
        super().__init__(asyncpg_pool, *args, **kwargs)
        if asyncpg is None:
            raise RuntimeError("Please install asyncpg")
        if not isinstance(asyncpg_pool, asyncpg.pool.Pool):
            raise TypeError("Expexted asyncpg.pool.Pool got {}".format(
                                type(asyncpg_pool)))
        if self._data_type == 'jsonb':
            self._encoder = json.dumps
            self._decoder = json.loads

    async def _execute_query(self, query, *params, fetchrow=False):
        async with self._driver_pool.acquire() as conn:
            if fetchrow:
                record = await conn.fetchrow(query, *params,
                                             timeout=self._timeout)
                return tuple(record.values()) if record else None
            else:
                await conn.execute(query, *params, timeout=self._timeout)


class PostgresqlAiopgStorage(PostgresqlAbstractStorage):
    """Postgresql aiopg storage"""

    def __init__(self, aiopg_pool, *args, **kwargs):
        super().__init__(aiopg_pool, *args, **kwargs)
        if aiopg is None:
            raise RuntimeError("Please install aiopg")
        if not isinstance(aiopg_pool, aiopg.pool.Pool):
            raise TypeError("Expexted aiopg.pool.Pool got {}".format(
                                type(aiopg_pool)))
        if self._data_type == 'jsonb':
            from psycopg2.extras import Json
            self._encoder = Json
            self._decoder = lambda x: x

    def _prepare_queries(self):
        super()._prepare_queries()
        self._query_delete_expired_sessions = \
            RE_QUERY_PARAMS.sub(' %s ', self._query_delete_expired_sessions)
        self._query_load_session = \
            RE_QUERY_PARAMS.sub(' %s ', self._query_load_session)
        self._query_save_session = \
            RE_QUERY_PARAMS.sub(' %s ', self._query_save_session)

    async def _execute_query(self, query, *params, fetchrow=False):
        async with self._driver_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, parameters=params,
                                  timeout=self._timeout)
                if fetchrow:
                    return await cur.fetchone()
