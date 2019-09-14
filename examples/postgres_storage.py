try:
    import aiopg
except ImportError:  # pragma: no cover
    aiopg = None
import json
import uuid
import warnings

import psycopg2.extras

from distutils.version import StrictVersion
from aiohttp_session import AbstractStorage, Session


class PgStorage(AbstractStorage):
    """PG storage"""

    def __init__(self, pg_pool, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 key_factory=lambda: uuid.uuid4(),
                 encoder=psycopg2.extras.Json, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        self._pg = pg_pool
        self._key_factory = key_factory

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        data = {}
        if cookie is None:
            return Session(None, data={}, new=True, max_age=self.max_age)
        else:
            async with self._pg.acquire() as conn:
                key = uuid.UUID(cookie)
                async with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

                    await cur.execute("SELECT session, extract(epoch from created) FROM web.sessions WHERE uuid = %s", (key,))
                    data = await cur.fetchone()

                    if not data:
                        return Session(None, data={},
                                       new=True, max_age=self.max_age)

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

        data = self._get_session_data(session)
        data['session'] = self._encoder(data['session'])
        expire = session.created + (session.max_age or 0)
        async with self._pg.acquire() as conn:
            async with conn.cursor() as cur:

                await cur.execute("INSERT INTO web.sessions (uuid,session,created,expire)"
                    " VALUES (%s, %s, to_timestamp(%s),to_timestamp(%s))"
                    " ON CONFLICT (uuid)"
                    " DO UPDATE"
                    " SET (session,expire)=(EXCLUDED.session, EXCLUDED.expire)", [key, data['session'],session.created,expire])
