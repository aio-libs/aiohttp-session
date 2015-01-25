import asyncio
import json
from . import AbstractStorage, Session, SESSION_KEY


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
    def save_session(self, request, response):
        session = request[SESSION_KEY]
        if not session._changed:
            return

        cookie_data = json.dumps(session._mapping)
        self.store_cookie(response, cookie_data)
