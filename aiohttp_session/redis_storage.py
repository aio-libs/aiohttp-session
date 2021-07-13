import json
import uuid
import warnings
from distutils.version import StrictVersion
from typing import Any, Callable, Optional

from aiohttp import web

from . import AbstractStorage, Session

try:
    import aioredis
except ImportError:  # pragma: no cover
    aioredis = None


class RedisStorage(AbstractStorage):
    """Redis storage"""

    def __init__(  # type: ignore[no-any-unimported]  # TODO: aioredis
        self,
        redis_pool: 'aioredis.commands.Redis', *,
        cookie_name: str = "AIOHTTP_SESSION",
        domain: Optional[str] = None,
        max_age: Optional[int] = None,
        path: str = '/',
        secure: Optional[bool] = None,
        httponly: bool = True,
        key_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        encoder: Callable[[object], str] = json.dumps,
        decoder: Callable[[str], Any] = json.loads
    ) -> None:
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
            raise TypeError("Expected aioredis.commands.Redis got {}".format(type(redis_pool)))
        self._redis = redis_pool

    async def load_session(self, request: web.Request) -> Session:
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

    async def save_session(
        self,
        request: web.Request,
        response: web.StreamResponse,
        session: Session
    ) -> None:
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


class EncryptedRedisStorage(AbstractStorage):
    """Redis storage Upgrade.

    Added possibilities to delete key from redis and encrypt cookie data.
    """

    def __init__(  # type: ignore[no-any-unimported]
        self,
        redis_pool: 'aioredis.commands.Redis',
        secret_key: Union[str, bytes, bytearray], *,
        cookie_name: str = "AIOHTTP_SESSION",
        domain: Optional[str] = None,
        max_age: Optional[int] = None,
        path: str = '/',
        secure: Optional[bool] = None,
        httponly: bool = True,
        key_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        encoder: Callable[[object], str] = json.dumps,
        decoder: Callable[[str], Any] = json.loads
    ) -> None:
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
            raise TypeError("Expected aioredis.commands.Redis got {}".format(type(redis_pool)))
        self._redis = redis_pool

        if isinstance(secret_key, str):
            pass
        elif isinstance(secret_key, (bytes, bytearray)):
            secret_key = base64.urlsafe_b64encode(secret_key)
        self._fernet = fernet.Fernet(secret_key)

    async def load_session(self, request: web.Request) -> Session:
        """Load session."""
        cookie = self.load_cookie(request)

        # No cookies - create empty session.
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            try:
                with await self._redis as conn:

                    # Decrypt cookies
                    dec = self._fernet.decrypt(cookie.encode('utf-8'), ttl=self.max_age).decode('utf-8')

                    key = str(dec)

                    # Get session from redis
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

            except InvalidToken:
                log.warning("Cannot decrypt cookie value, "
                            "create a new fresh session")
                return Session(None, data=None, new=True, max_age=self.max_age)

    async def save_session(
        self,
        request: web.Request,
        response: web.StreamResponse,
        session: Session
    ) -> None:
        """Save session."""

        key = session.identity

        if key is None:

            # No key - then create it
            key = self._key_factory()

            key_cookie = key.encode('utf-8')

            # Encrypt, save cookies.
            enc = self._fernet.encrypt(key_cookie).decode('utf-8')

            self.save_cookie(
                response,
                enc,
                max_age=session.max_age
            )
        else:
            # Empty session - save empty cookies
            if session.empty:
                self.save_cookie(response, '',
                                 max_age=session.max_age)
            else:
                key = str(key)

                key_cookie = key.encode('utf-8')

                enc = self._fernet.encrypt(key_cookie).decode('utf-8')

                self.save_cookie(
                    response,
                    enc,
                    max_age=session.max_age
                )

        data = self._encoder(self._get_session_data(session))

        # Save to redis.
        with await self._redis as conn:
            max_age = session.max_age
            expire = max_age if max_age is not None else 0
            await conn.set(self.cookie_name + '_' + key, data, expire=expire)

    async def delete_session(self, response: web.StreamResponse, session: Session) -> None:
        """Delete session."""
        key = session.identity

        with await self._redis as conn:
            # Delete from redis.
            await conn.delete(self.cookie_name + '_' + key)

        # Delete from cookies.
        self.save_cookie(response, '', max_age=session.max_age)

        """Example:

        @routes.get('/logout')
        async def logout(request: web.Request):
            session = await get_session(request)

            # Create response
            response = web.Response(status=200)

            # Delete session (from redis and cookies)
            await request.app.session_storage.delete_session(response, session)

            return response
        """
