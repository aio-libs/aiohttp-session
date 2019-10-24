import json
import uuid
from time import time
from . import AbstractStorage, Session


class MemcachedStorage(AbstractStorage):
    """Memcached storage"""

    def __init__(self, memcached_conn, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 key_factory=lambda: uuid.uuid4().hex,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        self._key_factory = key_factory
        self.conn = memcached_conn

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            key = str(cookie)
            stored_key = (self.cookie_name + '_' + key).encode('utf-8')
            data = await self.conn.get(stored_key)
            if data is None:
                return Session(None, data=None,
                               new=True, max_age=self.max_age)
            data = data.decode('utf-8')
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
        max_age = session.max_age
        # https://github.com/memcached/memcached/wiki/Programming#expiration
        # "Expiration times can be set from 0, meaning "never expire", to
        # 30 days. Any time higher than 30 days is interpreted as a Unix
        # timestamp date. If you want to expire an object on January 1st of
        # next year, this is how you do that."
        if max_age is None:
            expire = 0
        elif max_age > 30*24*60*60:
            expire = int(time()) + max_age
        else:
            expire = max_age
        stored_key = (self.cookie_name + '_' + key).encode('utf-8')
        await self.conn.set(
                                stored_key, data.encode('utf-8'),
                                exptime=expire)
