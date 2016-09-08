import asyncio
import json
import base64

from cryptography import fernet
from cryptography.fernet import InvalidToken

from . import AbstractStorage, Session
from .log import log


class EncryptedCookieStorage(AbstractStorage):
    """Encrypted JSON storage.
    """

    def __init__(self, secret_key, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)

        if isinstance(secret_key, str):
            pass
        elif isinstance(secret_key, (bytes, bytearray)):
            secret_key = base64.urlsafe_b64encode(secret_key)
        self._fernet = fernet.Fernet(secret_key)

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            try:
                data = json.loads(
                    self._fernet.decrypt(
                        cookie.encode('utf-8')).decode('utf-8'))
                return Session(None, data=data,
                               new=False, max_age=self.max_age)
            except InvalidToken:
                log.warning("Cannot decrypt cookie value, "
                            "create a new fresh session")
                return Session(None, data=None, new=True, max_age=self.max_age)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        if session.empty:
            return self.save_cookie(response, session._mapping,
                                    max_age=session.max_age)

        cookie_data = json.dumps(
            self._get_session_data(session)
        ).encode('utf-8')
        self.save_cookie(
            response,
            self._fernet.encrypt(cookie_data).decode('utf-8'),
            max_age=session.max_age
        )
