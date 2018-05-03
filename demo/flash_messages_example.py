import base64
from cryptography import fernet
from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


def flash(request, message):
    request.setdefault('flash_outgoing', []).append(message)


def get_messages(request):
    return request.pop('flash_incoming')


async def flash_middleware(app, handler):
    async def process(request):
        session = await get_session(request)
        request['flash_incoming'] = session.pop('flash', [])
        response = await handler(request)
        session['flash'] = (request.get('flash_incoming', []) +
                            request.get('flash_outgoing', []))
        return response
    return process


async def flash_handler(request):
    flash(request, 'You have just visited flash page')
    return web.HTTPFound('/')


async def handler(request):
    text = 'No flash messages yet'
    messages = get_messages(request)
    if messages:
        text = 'Messages: {}'.format(','.join(messages))
    return web.Response(text=text)


def make_app():
    app = web.Application()
    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))
    app.router.add_get('/', handler)
    app.router.add_get('/flash', flash_handler)
    # Install flash middleware
    app.middlewares.append(flash_middleware)
    return app


web.run_app(make_app())

