"""User sessions for aiohttp.web."""

import abc

import json
import time

from collections.abc import MutableMapping

from aiohttp import web
from aiohttp.web_middlewares import _Handler, _Middleware

from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Iterator,
    Optional,
    Tuple,
)
from typing_extensions import TypedDict

_TCookieParams = TypedDict(
    '_TCookieParams',
    {
        "domain": Optional[str],
        "max_age": Optional[int],
        "path": str,
        "secure": Optional[bool],
        "httponly": bool,
        "expires": str,
    },
    total=False
)

__version__ = '2.9.0'


class Session(MutableMapping):

    """Session dict-like object."""

    def __init__(
        self,
        identity: Optional[Any], *,
        data: Optional[Dict[Any, Any]],
        new: bool,
        max_age: Optional[int] = None
    ) -> None:
        self._changed = False
        self._mapping = {}  # type: Dict[Any, Any]
        self._identity = identity if data != {} else None
        self._new = new if data != {} else True
        self._max_age = max_age
        created = data.get('created', None) if data else None
        session_data = data.get('session', None) if data else None
        now = int(time.time())
        age = now - created if created else now
        if max_age is not None and age > max_age:
            session_data = None
        if self._new or created is None:
            self._created = now
        else:
            self._created = created

        if session_data is not None:
            self._mapping.update(session_data)

    def __repr__(self) -> str:
        return '<{} [new:{}, changed:{}, created:{}] {!r}>'.format(
            self.__class__.__name__, self.new, self._changed,
            self.created, self._mapping)

    @property
    def new(self) -> bool:
        return self._new

    @property
    def identity(self) -> Optional[Any]:
        return self._identity

    @property
    def created(self) -> int:
        return self._created

    @property
    def empty(self) -> bool:
        return not bool(self._mapping)

    @property
    def max_age(self) -> Optional[int]:
        return self._max_age

    @max_age.setter
    def max_age(self, value: Optional[int]) -> None:
        self._max_age = value

    def changed(self) -> None:
        self._changed = True

    def invalidate(self) -> None:
        self._changed = True
        self._mapping = {}

    def set_new_identity(self, identity: Optional[Any]) -> None:
        if not self._new:
            raise RuntimeError(
                "Can't change identity for a session which is not new")

        self._identity = identity

    def __len__(self) -> int:
        return len(self._mapping)

    def __iter__(self) -> Iterator[Tuple[Hashable, Any]]:
        return iter(self._mapping)

    def __contains__(self, key: Hashable) -> bool:
        return key in self._mapping

    def __getitem__(self, key: Hashable) -> Any:
        return self._mapping[key]

    def __setitem__(self, key: Hashable, value: Any) -> None:
        self._mapping[key] = value
        self._changed = True

    def __delitem__(self, key: Hashable) -> None:
        del self._mapping[key]
        self._changed = True


SESSION_KEY = 'aiohttp_session'
STORAGE_KEY = 'aiohttp_session_storage'


async def get_session(request: web.Request) -> Session:
    session = request.get(SESSION_KEY)
    if session is None:
        storage = request.get(STORAGE_KEY)
        if storage is None:
            raise RuntimeError(
                "Install aiohttp_session middleware "
                "in your aiohttp.web.Application")
        else:
            session = await storage.load_session(request)
            if not isinstance(session, Session):
                raise RuntimeError(
                    "Installed {!r} storage should return session instance "
                    "on .load_session() call, got {!r}.".format(storage,
                                                                session))
            request[SESSION_KEY] = session
    return session


async def new_session(request: web.Request) -> Session:
    storage = request.get(STORAGE_KEY)
    if storage is None:
        raise RuntimeError(
            "Install aiohttp_session middleware "
            "in your aiohttp.web.Application")
    else:
        session = await storage.new_session()
        if not isinstance(session, Session):
            raise RuntimeError(
                "Installed {!r} storage should return session instance "
                "on .load_session() call, got {!r}.".format(storage, session))
        request[SESSION_KEY] = session
    return session


def session_middleware(storage: 'AbstractStorage') -> _Middleware:

    if not isinstance(storage, AbstractStorage):
        raise RuntimeError("Expected AbstractStorage got {}".format(storage))

    @web.middleware
    async def factory(
        request: web.Request,
        handler: _Handler
    ) -> web.StreamResponse:
        request[STORAGE_KEY] = storage
        raise_response = False
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
            raise_response = True
        if not isinstance(response, (web.StreamResponse, web.HTTPException)):
            raise RuntimeError(
                "Expect response, not {!r}".format(type(response)))
        if not isinstance(response, (web.Response, web.HTTPException)):
            # likely got websocket or streaming
            return response
        if response.prepared:
            raise RuntimeError(
                "Cannot save session data into prepared response")
        session = request.get(SESSION_KEY)
        if session is not None:
            if session._changed:
                await storage.save_session(request, response, session)
        if raise_response:
            raise response
        return response

    return factory


def setup(app: web.Application, storage: 'AbstractStorage') -> None:
    """Setup the library in aiohttp fashion."""

    app.middlewares.append(session_middleware(storage))


class AbstractStorage(metaclass=abc.ABCMeta):

    def __init__(
        self, *,
        cookie_name: str = "AIOHTTP_SESSION",
        domain: Optional[str] = None,
        max_age: Optional[int] = None,
        path: str = '/',
        secure: Optional[bool] = None,
        httponly: bool = True,
        encoder: Callable[..., str] = json.dumps,
        decoder: Callable[..., Dict[Any, Any]] = json.loads
    ) -> None:
        self._cookie_name = cookie_name
        self._cookie_params = dict(
            domain=domain,
            max_age=max_age,
            path=path,
            secure=secure,
            httponly=httponly
        )  # type: _TCookieParams
        self._max_age = max_age
        self._encoder = encoder
        self._decoder = decoder

    @property
    def cookie_name(self) -> str:
        return self._cookie_name

    @property
    def max_age(self) -> Optional[int]:
        return self._max_age

    @property
    def cookie_params(self) -> _TCookieParams:
        return self._cookie_params

    def _get_session_data(self, session: Session) -> Dict[str, Any]:
        if not session.empty:
            data = {
                'created': session.created,
                'session': session._mapping
            }
        else:
            data = {}
        return data

    async def new_session(self) -> Session:
        return Session(None, data=None, new=True, max_age=self.max_age)

    @abc.abstractmethod
    async def load_session(self, request: web.Request) -> Session:
        pass

    @abc.abstractmethod
    async def save_session(
        self,
        request: web.Request,
        response: web.StreamResponse,
        session: Session
    ) -> None:
        pass

    def load_cookie(self, request: web.Request) -> Optional[str]:
        cookie = request.cookies.get(self._cookie_name)  # type: Optional[str]
        return cookie

    def save_cookie(
        self,
        response: web.StreamResponse,
        cookie_data: str, *,
        max_age: Optional[int] = None
    ) -> None:
        params = self._cookie_params.copy()  # type: _TCookieParams
        if max_age is not None:
            params['max_age'] = max_age
            params['expires'] = time.strftime(
                "%a, %d-%b-%Y %T GMT",
                time.gmtime(time.time() + max_age))
        if not cookie_data:
            response.del_cookie(
                self._cookie_name,
                domain=params["domain"],
                path=params["path"],
                )
        else:
            response.set_cookie(self._cookie_name, cookie_data, **params)


class SimpleCookieStorage(AbstractStorage):
    """Simple JSON storage.

    Doesn't any encryption/validation, use it for tests only"""

    def __init__(
        self, *,
        cookie_name: str = "AIOHTTP_SESSION",
        domain: Optional[str] = None,
        max_age: Optional[int] = None,
        path: str = '/',
        secure: Optional[bool] = None,
        httponly: bool = True,
        encoder: Callable[..., str] = json.dumps,
        decoder: Callable[..., Dict[Any, Any]] = json.loads
    ) -> None:
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)

    async def load_session(self, request: web.Request) -> Session:
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            data = self._decoder(cookie)
            return Session(None, data=data, new=False, max_age=self.max_age)

    async def save_session(
        self,
        request: web.Request,
        response: web.StreamResponse,
        session: Session
    ) -> None:
        cookie_data = self._encoder(self._get_session_data(session))
        self.save_cookie(response, cookie_data, max_age=session.max_age)
