import asyncio
import json
import uuid

from . import AbstractStorage, Session, SESSION_KEY


class RedisStorage(AbstractStorage):
    """Redis storage"""

    def __init__(self, redis_pool, identity="AIOHTTP_COOKIE_SESSION", *,
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(identity, domain=domain, max_age=max_age,
                         path=path, secure=secure, httponly=httponly)
        self._encoder = encoder
        self._decoder = decoder
        self._redis = redis_pool

    @asyncio.coroutine
    def make_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            session = Session(None, new=True)
        else:
            with (yield from self._redis) as conn:
                key = self.identity + '_' + str(cookie)
                data = yield from conn.get(cookie)
                data = data.decode('utf-8')
                data = self._decoder(data)
                session = Session(key, data=data, new=False)

        request[SESSION_KEY] = session

    @asyncio.coroutine
    def save_session(self, request, response, session):
        key = session.identity
        if key is None:
            key = self.identity + '_' + uuid.uuid4().hex
            self.store_cookie(response, key)
        else:
            key = str(key)
            self.store_cookie(response, key)
        data = self._encoder(session._mapping)
        with (yield from self._redis) as conn:
            max_age = self.max_age
            expire = max_age if max_age is not None else 0
            yield from conn.set(key, data, expire=expire)
