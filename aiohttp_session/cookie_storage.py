import asyncio
import json
import base64
from . import AbstractStorage, Session, SESSION_KEY

from Crypto.Cipher import AES
from Crypto import Random


class EncryptedCookieStorage(AbstractStorage):
    """Encrypted JSON storage.
    """

    def __init__(self, secret_key, identity="AIOHTTP_COOKIE_SESSION", *,
                 domain=None, max_age=None, path='/',
                 secure=None, httponly=True):
        super().__init__(identity, domain=domain, max_age=max_age,
                         path=path, secure=secure, httponly=httponly)

        self._secret_key = secret_key
        if len(self._secret_key) % AES.block_size != 0:
            raise TypeError(
                'Secret key must be a multiple of {} in length'.format(
                    AES.block_size))

    @asyncio.coroutine
    def make_session(self, request):
        cookie = self.load_cookie(request)
        if cookie is None:
            session = Session(self.identity, new=True)
        else:
            cookie = base64.b64decode(cookie)
            iv = cookie[:AES.block_size]
            data = cookie[AES.block_size:]
            cipher = AES.new(self._secret_key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(data)
            data = json.loads(decrypted.decode('utf-8'))
            session = Session(self.identity, data=data, new=False)

        request[SESSION_KEY] = session

    @asyncio.coroutine
    def save_session(self, request, response, session):
        cookie_data = json.dumps(session._mapping).encode('utf-8')
        if len(cookie_data) % AES.block_size != 0:
            # padding with spaces to full blocks
            to_pad = AES.block_size - (len(cookie_data) % AES.block_size)
            cookie_data += b' ' * to_pad

        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self._secret_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(cookie_data)
        encrypted = iv + encrypted
        b64coded = base64.b64encode(encrypted).decode('utf-8')
        self.store_cookie(response, b64coded)
