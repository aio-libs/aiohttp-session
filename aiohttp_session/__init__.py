"""User sessions for aiohttp.web."""

import abc
import asyncio
from collections import MutableMapping
import json
import time

from aiohttp import web


__version__ = '0.7.1'


class Session(MutableMapping):

    """Session dict-like object."""

    def __init__(self, identity, *, data, new, max_age=None):
        self._changed = False
        self._mapping = {}
        self._identity = identity
        self._new = new
        self._max_age = max_age
        created = data.get('created', None) if data else None
        session_data = data.get('session', None) if data else None

        if new or created is None:
            self._created = int(time.time())
        else:
            self._created = created

        if session_data is not None:
            self._mapping.update(session_data)

    def __repr__(self):
        return '<{} [new:{}, changed:{}, created:{}] {!r}>'.format(
            self.__class__.__name__, self.new, self._changed,
            self.created, self._mapping)

    @property
    def new(self):
        return self._new

    @property
    def identity(self):
        return self._identity

    @property
    def created(self):
        return self._created

    @property
    def empty(self):
        return not bool(self._mapping)

    @property
    def max_age(self):
        return self._max_age

    @max_age.setter
    def max_age(self, value):
        self._max_age = value

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
    session = request.get(SESSION_KEY)
    if session is None:
        storage = request.get(STORAGE_KEY)
        if storage is None:
            raise RuntimeError(
                "Install aiohttp_session middleware "
                "in your aiohttp.web.Application")
        else:
            session = yield from storage.load_session(request)
            if not isinstance(session, Session):
                raise RuntimeError(
                    "Installed {!r} storage should return session instance "
                    "on .load_session() call, got {!r}.".format(storage,
                                                                session))
            request[SESSION_KEY] = session
    return session


def session_middleware(storage):

    assert isinstance(storage, AbstractStorage), storage

    @asyncio.coroutine
    def factory(app, handler):

        @asyncio.coroutine
        def middleware(request):
            request[STORAGE_KEY] = storage
            raise_response = False
            try:
                response = yield from handler(request)
            except web.HTTPException as exc:
                response = exc
                raise_response = True
            if not isinstance(response, web.StreamResponse):
                raise RuntimeError("Expect response, not {!r}", type(response))
            if not isinstance(response, web.Response):
                # likely got websoket or streaming
                return response
            if response.prepared:
                raise RuntimeError(
                    "Cannot save session data into prepared response")
            session = request.get(SESSION_KEY)
            if session is not None:
                if session._changed:
                    yield from storage.save_session(request, response, session)
            if raise_response:
                raise response
            return response

        return middleware

    return factory


def setup(app, storage):
    """Setup the library in aiohttp fashion."""

    app.middlewares.append(session_middleware(storage))


class AbstractStorage(metaclass=abc.ABCMeta):

    def __init__(self, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        self._cookie_name = cookie_name
        self._cookie_params = dict(domain=domain,
                                   max_age=max_age,
                                   path=path,
                                   secure=secure,
                                   httponly=httponly)
        self._max_age = max_age

    @property
    def cookie_name(self):
        return self._cookie_name

    @property
    def max_age(self):
        return self._max_age

    @property
    def cookie_params(self):
        return self._cookie_params

    def _get_session_data(self, session):
        if not session.empty:
            data = {
                'created': session.created,
                'session': session._mapping
            }
        else:
            data = {}
        return data

    @asyncio.coroutine
    @abc.abstractmethod
    def load_session(self, request):
        pass

    @asyncio.coroutine
    @abc.abstractmethod
    def save_session(self, request, response, session):
        pass

    def load_cookie(self, request):
        cookie = request.cookies.get(self._cookie_name)
        return cookie

    def save_cookie(self, response, cookie_data, *, max_age=None):
        params = dict(self._cookie_params)
        if max_age is not None:
            params['max_age'] = max_age
            params['expires'] = time.strftime(
                "%a, %d-%b-%Y %T GMT",
                time.gmtime(time.monotonic() + max_age))
        if not cookie_data:
            response.del_cookie(self._cookie_name)
        else:
            response.set_cookie(self._cookie_name, cookie_data, **params)


class SimpleCookieStorage(AbstractStorage):
    """Simple JSON storage.

    Doesn't any encryption/validation, use it for tests only"""

    def __init__(self, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            data = json.loads(cookie)
            return Session(None, data=data, new=False, max_age=self.max_age)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        cookie_data = json.dumps(self._get_session_data(session))
        self.save_cookie(response, cookie_data, max_age=session.max_age)
