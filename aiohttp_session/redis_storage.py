try:
    import aioredis
except ImportError:  # pragma: no cover
    aioredis = None
import json
import uuid
import warnings

from distutils.version import StrictVersion
from . import AbstractStorage, Session


class RedisStorage(AbstractStorage):
    """Redis storage"""

    def __init__(self, redis_pool, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 key_factory=lambda: uuid.uuid4().hex,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)
        if aioredis is None:
            raise RuntimeError("Please install aioredis")
        if StrictVersion(aioredis.__version__).version < (1, 0):
            raise RuntimeError("aioredis<1.0 is not supported")
        self._key_factory = key_factory
        if isinstance(redis_pool, aioredis.pool.ConnectionsPool):
            warnings.warn(
                "using a pool created with aioredis.create_pool is deprecated"
                "please use a pool created with aioredis.create_redis_pool",
                DeprecationWarning
            )
            redis_pool = aioredis.commands.Redis(redis_pool)
        elif not isinstance(redis_pool, aioredis.commands.Redis):
            raise TypeError("Expexted aioredis.commands.Redis got {}".format(
                    type(redis_pool)))
        self._redis = redis_pool

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            with await self._redis as conn:
                key = str(cookie)
                data = await conn.get(self.cookie_name + '_' + key)
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
        with await self._redis as conn:
            max_age = session.max_age
            expire = max_age if max_age is not None else 0
            await conn.set(self.cookie_name + '_' + key, data, expire=expire)
