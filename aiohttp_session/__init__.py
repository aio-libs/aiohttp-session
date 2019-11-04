"""User sessions for aiohttp.web."""

import abc

import json
import time

from collections.abc import MutableMapping

from aiohttp import web


__version__ = '2.9.0'


class Session(MutableMapping):

    """Session dict-like object."""

    def __init__(self, identity, *, data, new, max_age=None):
        self._changed = False
        self._mapping = {}
        self._identity = identity if data != {} else None
        self._new = new
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

    def set_new_identity(self, identity):
        if not self._new:
            raise RuntimeError(
                "Can't change identity for a session which is not new")

        self._identity = identity

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


async def get_session(request):
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


async def new_session(request):
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


def session_middleware(storage):

    if not isinstance(storage, AbstractStorage):
        raise RuntimeError("Expected AbstractStorage got {}".format(storage))

    @web.middleware
    async def factory(request, handler):
        request[STORAGE_KEY] = storage
        raise_response = False
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
            raise_response = True
        if not isinstance(response, web.StreamResponse):
            raise RuntimeError(
                "Expect response, not {!r}".format(type(response)))
        if not isinstance(response, web.Response):
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


def setup(app, storage):
    """Setup the library in aiohttp fashion."""

    app.middlewares.append(session_middleware(storage))


class AbstractStorage(metaclass=abc.ABCMeta):

    def __init__(self, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads):
        self._cookie_name = cookie_name
        self._cookie_params = dict(domain=domain,
                                   max_age=max_age,
                                   path=path,
                                   secure=secure,
                                   httponly=httponly)
        self._max_age = max_age
        self._encoder = encoder
        self._decoder = decoder

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

    async def new_session(self):
        return Session(None, data=None, new=True, max_age=self.max_age)

    @abc.abstractmethod
    async def load_session(self, request):
        pass

    @abc.abstractmethod
    async def save_session(self, request, response, session):
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

    def __init__(self, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            data = self._decoder(cookie)
            return Session(None, data=data, new=False, max_age=self.max_age)

    async def save_session(self, request, response, session):
        cookie_data = self._encoder(self._get_session_data(session))
        self.save_cookie(response, cookie_data, max_age=session.max_age)
