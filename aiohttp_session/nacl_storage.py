import asyncio
import json

import nacl.secret
import nacl.utils
from nacl.encoding import Base64Encoder

from . import AbstractStorage, Session


class NaClCookieStorage(AbstractStorage):
    """NaCl Encrypted JSON storage.
    """

    def __init__(self, secret_key, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)

        self._secretbox = nacl.secret.SecretBox(secret_key)

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, data=None, new=True, max_age=self.max_age)
        else:
            data = json.loads(
                self._secretbox.decrypt(cookie.encode('utf-8'),
                                        encoder=Base64Encoder).decode('utf-8')
            )
            return Session(None, data=data, new=False, max_age=self.max_age)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        if session.empty:
            return self.save_cookie(response, session._mapping,
                                    max_age=session.max_age)

        cookie_data = json.dumps(
            self._get_session_data(session)
        ).encode('utf-8')
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        self.save_cookie(
            response,
            self._secretbox.encrypt(cookie_data, nonce,
                                    encoder=Base64Encoder).decode('utf-8'),
            max_age=session.max_age
        )
