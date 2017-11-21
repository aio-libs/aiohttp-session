import json
import uuid

from . import AbstractStorage, Session


class MemcachedStorage(AbstractStorage):
    """Memcached storage"""

    def __init__(self, memcached_conn, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads,
                 key_factory=lambda: uuid.uuid4().hex):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)
        self._encoder = encoder
        self._decoder = decoder
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
        expire = max_age if max_age is not None else 0
        stored_key = (self.cookie_name + '_' + key).encode('utf-8')
        await self.conn.set(
                                stored_key, data.encode('utf-8'),
                                exptime=expire)
