import abc
import asyncio
from collections import MutableMapping
import json

from aiohttp import web


__version__ = '0.0.1'


class Session(MutableMapping):
    """Session dict-like object.
    """

    def __init__(self, identity, *, data=None, new=False):
        self._changed = False
        self._mapping = {}
        self._identity = identity
        self._new = new
        if data is not None:
            self._mapping.update(data)

    def __repr__(self):
        return '<{} [new:{}, changed:{}] {!r}>'.format(
            self.__class__.__name__, self.new, self._changed,
            self._mapping)

    @property
    def new(self):
        return self._new

    @property
    def identity(self):
        return self._identity

    def changed(self):
        self._changed = True

    def invalidate(self):
        self._changed = True
        self._mapping = {}

    def __len__(self):
        return len(self._mapping)

    def __iter__(self):
        return iter(self._mapping)

    def __contains__(self, key):
        return key in self._mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def __setitem__(self, key, value):
        self._mapping[key] = value
        self._changed = True

    def __delitem__(self, key):
        del self._mapping[key]
        self._changed = True


SESSION_KEY = 'aiohttp_session'
STORAGE_KEY = 'aiohttp_session_storage'


@asyncio.coroutine
def get_session(request):
    ret = request.get(SESSION_KEY)
    if ret is None:
        storage = request.get(STORAGE_KEY)
        if storage is None:
            raise RuntimeError(
                "Install aiohttp_session middleware "
                "in your aiohttp.web.Application")
        else:
            yield from storage.make_session(request)
            ret = request.get(SESSION_KEY)
            if ret is None:
                raise RuntimeError(
                    "Installed {!r} storage should fill request[SESSION_KEY] "
                    "on .make_session() call.")
    return ret


def session_middleware(storage):

    assert isinstance(storage, AbstractStorage), storage

    @asyncio.coroutine
    def factory(app, handler):

        @asyncio.coroutine
        def middleware(request):
            request[STORAGE_KEY] = storage
            response = yield from handler(request)
            if not isinstance(response, web.StreamResponse):
                raise RuntimeError("Expect response, not {!r}", type(response))
            if not isinstance(response, web.Response):
                # likely got websoket or streaming
                return response
            if response.started:
                raise RuntimeError(
                    "Cannot save session data into started response")
            session = request.get(SESSION_KEY)
            if session is not None:
                if session._changed:
                    yield from storage.save_session(request, response, session)
            return response

        return middleware

    return factory


class AbstractStorage(metaclass=abc.ABCMeta):

    def __init__(self, identity="AIOHTTP_SESSION", *,
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        self._identity = identity
        self._cookie_params = dict(domain=domain,
                                   max_age=max_age,
                                   path=path,
                                   secure=secure,
                                   httponly=httponly)
        self._max_age = max_age

    @property
    def identity(self):
        return self._identity

    @property
    def max_age(self):
        return self._max_age

    @property
    def cookie_params(self):
        return self._cookie_params

    @asyncio.coroutine
    @abc.abstractmethod
    def make_session(self, request):
        pass

    @asyncio.coroutine
    @abc.abstractmethod
    def save_session(self, request, response, session):
        pass

    def load_cookie(self, request):
        cookie = request.cookies.get(self._identity)
        return cookie

    def store_cookie(self, response, cookie_data):
        if not cookie_data:
            response.del_cookie(self._identity)
        else:
            response.set_cookie(self._identity, cookie_data,
                                **self._cookie_params)


class SimpleCookieStorage(AbstractStorage):
    """Simple JSON storage.

    Doesn't any encryption/validation, use it for tests only"""

    def __init__(self, identity="AIOHTTP_COOKIE_SESSION", *,
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(identity, domain=domain, max_age=max_age,
                         path=path, secure=secure, httponly=httponly)

    @asyncio.coroutine
    def make_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            session = Session(self.identity, new=True)
        else:
            data = json.loads(cookie)
            session = Session(self.identity, data=data, new=False)

        request[SESSION_KEY] = session

    @asyncio.coroutine
    def save_session(self, request, response, session):
        cookie_data = json.dumps(session._mapping)
        self.store_cookie(response, cookie_data)
