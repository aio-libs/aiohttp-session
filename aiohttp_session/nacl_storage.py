import binascii
import json
from typing import Any, Callable, Optional

import nacl.exceptions
import nacl.secret
import nacl.utils
from aiohttp import web
from nacl.encoding import Base64Encoder

from . import AbstractStorage, Session
from .log import log


class NaClCookieStorage(AbstractStorage):
    """NaCl Encrypted JSON storage."""

    def __init__(
        self,
        secret_key: bytes,
        *,
        cookie_name: str = "AIOHTTP_SESSION",
        domain: Optional[str] = None,
        max_age: Optional[int] = None,
        path: str = "/",
        secure: Optional[bool] = None,
        httponly: bool = True,
        samesite: Optional[str] = None,
        encoder: Callable[[object], str] = json.dumps,
        decoder: Callable[[str], Any] = json.loads
    ) -> None:
        super().__init__(
            cookie_name=cookie_name,
            domain=domain,
            max_age=max_age,
            path=path,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
            encoder=encoder,
            decoder=decoder,
        )

        self._secretbox = nacl.secret.SecretBox(secret_key)

    def empty_session(self) -> Session:
        return Session(None, data=None, new=True, max_age=self.max_age)

    async def load_session(self, request: web.Request) -> Session:
        cookie = self.load_cookie(request)
        if cookie is None:
            return self.empty_session()
        else:
            try:
                data = self._decoder(
                    self._secretbox.decrypt(
                        cookie.encode("utf-8"), encoder=Base64Encoder
                    ).decode("utf-8")
                )
                return Session(None, data=data, new=False, max_age=self.max_age)
            except (binascii.Error, nacl.exceptions.CryptoError):
                log.warning(
                    "Cannot decrypt cookie value, " "create a new fresh session"
                )
                return self.empty_session()

    async def save_session(
        self, request: web.Request, response: web.StreamResponse, session: Session
    ) -> None:
        if session.empty:
            return self.save_cookie(response, "", max_age=session.max_age)

        cookie_data = self._encoder(self._get_session_data(session)).encode("utf-8")
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        self.save_cookie(
            response,
            self._secretbox.encrypt(cookie_data, nonce, encoder=Base64Encoder).decode(
                "utf-8"
            ),
            max_age=session.max_age,
        )
