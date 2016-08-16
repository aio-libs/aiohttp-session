import asyncio
import json
import uuid

from cryptography import fernet
from cryptography.fernet import InvalidToken

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
            return Session(None, data=None, new=True)
        else:
            with (yield from self._redis) as conn:
                key = str(cookie)
                data = yield from conn.get(self.cookie_name + '_' + key)
                if data is None:
                    return Session(None, data=None, new=True)
                data = data.decode('utf-8')
                data = self._decoder(data)
                return Session(key, data=data, new=False)

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
            max_age = self.max_age
            expire = max_age if max_age is not None else 0
            yield from conn.set(self.cookie_name + '_' + key,
                                data, expire=expire)


class EncryptedRedisStorage(AbstractStorage):
    """Encrypted Redis storage"""

    def __init__(self, redis_pool, secret_key, *,
                 cookie_name="AIOHTTP_SESSION", domain=None,
                 encoder=json.dumps, decoder=json.loads,
                 httponly=True, max_age=None, path='/', secure=None):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         httponly=httponly, max_age=max_age, path=path,
                         secure=secure)
        self._encoder = encoder
        self._decoder = decoder
        self._redis = redis_pool
        if isinstance(secret_key, str):
            secret_key = secret_key.encode('utf-8')
        self._fernet = fernet.Fernet(secret_key)

    @asyncio.coroutine
    def load_session(self, request):
        uuid_encrypted_string = self.load_cookie(request)
        if uuid_encrypted_string is None:
            return Session(None, data=None, new=True)
        else:
            uuid_encrypted_bytes = uuid_encrypted_string.encode('utf-8')
            try:
                uuid_bytes = self._fernet.decrypt(uuid_encrypted_bytes)
                uuid_string = uuid_bytes.decode('utf-8')
                with (yield from self._redis) as conn:
                    data = yield from conn.get(
                        self.cookie_name + '_' + uuid_string)
                    if data is None:
                        return Session(None, data=None, new=True)
                    data = data.decode('utf-8')
                    data = self._decoder(data)
                    return Session(uuid_encrypted_string, data=data, new=False)
            except InvalidToken:
                return Session(None, data=None, new=True)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        identity = session.identity
        if identity is None:
            uuid_string = uuid.uuid4().hex
            uuid_bytes = uuid_string.encode('utf-8')
            uuid_encrypted_bytes = self._fernet.encrypt(uuid_bytes)
            uuid_encrypted_string = uuid_encrypted_bytes.decode('utf-8')
        else:
            uuid_encrypted_string = str(identity)
            uuid_encrypted_bytes = uuid_encrypted_string.encode('utf=8')
            try:
                uuid_bytes = self._fernet.decrypt(uuid_encrypted_bytes)
                uuid_string = uuid_bytes.decode('utf-8')
            except InvalidToken:
                uuid_string = uuid.uuid4().hex
                uuid_bytes = uuid_string.encode('utf-8')
                uuid_encrypted_bytes = self._fernet.encrypt(uuid_bytes)
                uuid_encrypted_string = (
                    uuid_encrypted_bytes.decode('utf-8'))
        self.save_cookie(
            response,
            uuid_encrypted_string,
            max_age=session.max_age)
        data = self._encoder(self._get_session_data(session))
        with (yield from self._redis) as conn:
            max_age = self.max_age
            expire = max_age if max_age is not None else 0
            yield from conn.set(
                self.cookie_name + '_' + uuid_string,
                data,
                expire=expire)
