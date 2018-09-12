import binascii
import json

import nacl.secret
import nacl.utils
import nacl.exceptions
from nacl.encoding import Base64Encoder

from . import AbstractStorage, Session
from .log import log


class NaClCookieStorage(AbstractStorage):
    """NaCl Encrypted JSON storage.
    """

    def __init__(self, secret_key, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True,
                 encoder=json.dumps, decoder=json.loads):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly,
                         encoder=encoder, decoder=decoder)

        self._secretbox = nacl.secret.SecretBox(secret_key)

    def empty_session(self):
        return Session(None, data=None, new=True, max_age=self.max_age)

    async def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return self.empty_session()
        else:
            try:
                data = self._decoder(
                    self._secretbox.decrypt(
                        cookie.encode('utf-8'),
                        encoder=Base64Encoder).decode('utf-8')
                )
                return Session(None, data=data, new=False,
                               max_age=self.max_age)
            except (binascii.Error, nacl.exceptions.CryptoError):
                log.warning("Cannot decrypt cookie value, "
                            "create a new fresh session")
                return self.empty_session()

    async def save_session(self, request, response, session):
        if session.empty:
            return self.save_cookie(response, session._mapping,
                                    max_age=session.max_age)

        cookie_data = self._encoder(
            self._get_session_data(session)
        ).encode('utf-8')
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        self.save_cookie(
            response,
            self._secretbox.encrypt(cookie_data, nonce,
                                    encoder=Base64Encoder).decode('utf-8'),
            max_age=session.max_age
        )
