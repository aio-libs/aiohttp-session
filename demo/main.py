import base64
import time

from aiohttp import web
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet


async def handler(request: web.Request) -> web.Response:
    session = await get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(text=text)


def make_app() -> web.Application:
    app = web.Application()
    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))
    app.router.add_get('/', handler)
    return app


web.run_app(make_app())
