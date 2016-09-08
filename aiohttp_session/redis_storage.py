import asyncio
import json
import uuid

from . import AbstractStorage, Session


class RedisStorage(AbstractStorage):
    """Redis storage"""

    def __init__(self, redis_pool, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)
        self._encoder = encoder
        self._decoder = decoder
        self._redis = redis_pool

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            with (yield from self._redis) as conn:
                key = str(cookie)
                data = yield from conn.get(self.cookie_name + '_' + key)
                if data is None:
                    return Session(None, data=None,
                                   new=True, max_age=self.max_age)
                data = data.decode('utf-8')
                data = self._decoder(data)
                return Session(key, data=data, new=False, max_age=self.max_age)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        key = session.identity
        if key is None:
            key = uuid.uuid4().hex
            self.save_cookie(response, key,
                             max_age=session.max_age)
        else:
            key = str(key)
            self.save_cookie(response, key,
                             max_age=session.max_age)

        data = self._encoder(self._get_session_data(session))
        with (yield from self._redis) as conn:
            max_age = session.max_age
            expire = max_age if max_age is not None else 0
            yield from conn.set(self.cookie_name + '_' + key,
                                data, expire=expire)
