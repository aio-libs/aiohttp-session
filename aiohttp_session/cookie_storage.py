import asyncio
import json
import base64

from cryptography import fernet

from . import AbstractStorage, Session


class EncryptedCookieStorage(AbstractStorage):
    """Encrypted JSON storage.
    """

    def __init__(self, secret_key, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)

        self._fernet = fernet.Fernet(base64.urlsafe_b64encode(secret_key))

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, new=True)
        else:
            data = json.loads(
                self._fernet.decrypt(cookie.encode('utf-8')).decode('utf-8')
            )
            return Session(None, data=data, new=False)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        if session.empty:
            return self.save_cookie(response, session._mapping)

        cookie_data = json.dumps(
            self._get_session_data(session)
        ).encode('utf-8')
        self.save_cookie(
            response,
            self._fernet.encrypt(cookie_data).decode('utf-8'),
        )
