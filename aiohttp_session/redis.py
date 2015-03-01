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
            session = Session(self.identity, new=True)
        else:
            with (yield from self._redis) as conn:
                data = yield from conn.get(str(cookie))
                data = self._decoder(data)
                session = Session(self.identity, data=data, new=False)

        request[SESSION_KEY] = session

    @asyncio.coroutine
    def save_session(self, request, response):
        session = request[SESSION_KEY]
        if not session._changed:
            return
        cookie = self.load_cookie(request)
        if cookie is None:
            key = uuid.uuid4().hex
            self.store_cookie(response, key)
        else:
            key = str(cookie)
        data = self._encoder(session._mapping)
        with (yield from self._redis) as conn:
            yield from conn.set(key, data)
