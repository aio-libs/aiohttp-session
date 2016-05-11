import asyncio
import time
import os
from aiohttp import web
from aiohttp_session import setup, get_session, session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage

@asyncio.coroutine
def handler(request):
    session = yield from get_session(request)
    last_visit = session['last_visit'] if 'last_visit' in session else None
    session['last_visit'] = time.time()
    text = 'Last visited: {}'.format(last_visit)
    return web.Response(body=text.encode('utf-8'))

app = web.Application()
# secret_key must be 32 url-safe base64-encoded bytes
secret_key = os.urandom(32)
setup(app, EncryptedCookieStorage(secret_key))
app.router.add_route('GET', '/', handler)
web.run_app(app)

