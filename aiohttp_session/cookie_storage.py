import asyncio
import json
import base64
from . import AbstractStorage, Session

from cryptography.fernet import Fernet

key =  b'klef1rMWEwD5VGJHAMfBa7vwIygLblPRuODdJLX_C2U='

class EncryptedCookieStorage(AbstractStorage):
    """Encrypted JSON storage.
    """

    def __init__(self, secret_key, *, cookie_name="AIOHTTP_SESSION",
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(cookie_name=cookie_name, domain=domain,
                         max_age=max_age, path=path, secure=secure,
                         httponly=httponly)

        self._secret_key = secret_key

        if len(self._secret_key) < 44:
            raise TypeError(
                'Secret key must be a least {} in length'.format(
                    44))
        self.cipher = Fernet(key)

    @asyncio.coroutine
    def load_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            return Session(None, new=True)
        else:
            cookie = base64.b64decode(cookie)
            decrypted = self.cipher.decrypt(data)
            data = json.loads(decrypted.decode('utf-8'))
            return Session(None, data=data, new=False)

    @asyncio.coroutine
    def save_session(self, request, response, session):
        cookie_data = json.dumps(session._mapping).encode('utf-8')
        encrypted = self.cipher.encrypt(cookie_data)
        b64coded = base64.b64encode(encrypted).decode('utf-8')
        self.save_cookie(response, b64coded)
