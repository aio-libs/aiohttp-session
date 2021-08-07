import json
import uuid
from typing import Any, Callable, Optional

import psycopg2.extras
from aiohttp import web
from aiohttp_session import AbstractStorage, Session
from aiopg import Pool


class PgStorage(AbstractStorage):
    """PG storage"""

    def __init__(self, pg_pool: Pool, *, cookie_name: str = "AIOHTTP_SESSION",  # type: ignore[no-any-unimported] # noqa: B950
                 domain: Optional[str] = None, max_age: Optional[int] = None,
                 path: str = '/', secure: Optional[bool] = None, httponly: bool = True,
                 key_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
                 encoder: Callable[[object], str] = psycopg2.extras.Json,
                 decoder: Callable[[str], Any] = json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        self._pg = pg_pool
        self._key_factory = key_factory

    async def load_session(self, request: web.Request) -> Session:
        cookie = self.load_cookie(request)
        data = {}
        if cookie is None:
            return Session(None, data={}, new=True, max_age=self.max_age)
        else:
            async with self._pg.acquire() as conn:
                key = uuid.UUID(cookie)
                async with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

                    await cur.execute("SELECT session, extract(epoch from created) "  # noqa: S608
                                      + "FROM web.sessions WHERE uuid = %s", (key,))
                    data = await cur.fetchone()

                    if not data:
                        return Session(None, data={}, new=True, max_age=self.max_age)

            return Session(key, data=data, new=False, max_age=self.max_age)

    async def save_session(self, request: web.Request, response: web.StreamResponse,
                           session: Session) -> None:
        key = session.identity
        if key is None:
            key = self._key_factory()
            self.save_cookie(response, key, max_age=session.max_age)
        else:
            if session.empty:
                self.save_cookie(response, "", max_age=session.max_age)
            else:
                key = str(key)
                self.save_cookie(response, key, max_age=session.max_age)

        data = self._get_session_data(session)
        if not data:
            return

        data_encoded = self._encoder(data["session"])
        expire = data["created"] + (session.max_age or 0)
        async with self._pg.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO web.sessions (uuid,session,created,expire)"  # noqa: S608
                    + " VALUES (%s, %s, to_timestamp(%s),to_timestamp(%s))"  # noqa: S608
                    + " ON CONFLICT (uuid)"  # noqa: S608
                    + " DO UPDATE"  # noqa: S608
                    + " SET (session,expire)=(EXCLUDED.session, EXCLUDED.expire)",
                    [key, data_encoded, data["created"], expire])
