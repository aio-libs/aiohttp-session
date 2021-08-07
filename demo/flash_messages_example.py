import base64
from typing import Awaitable, Callable, List, NoReturn, cast

from aiohttp import web
from aiohttp_session import get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def flash(request: web.Request, message: str) -> None:
    request.setdefault('flash_outgoing', []).append(message)


def get_messages(request: web.Request) -> List[str]:
    return cast(List[str], request.pop('flash_incoming'))


async def flash_middleware(app: web.Application, handler: _Handler) -> _Handler:
    async def process(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        request['flash_incoming'] = session.pop('flash', [])
        response = await handler(request)
        session['flash'] = (request.get('flash_incoming', [])
                            + request.get('flash_outgoing', []))
        return response
    return process


async def flash_handler(request: web.Request) -> NoReturn:
    flash(request, 'You have just visited flash page')
    raise web.HTTPFound("/")


async def handler(request: web.Request) -> web.Response:
    text = 'No flash messages yet'
    messages = get_messages(request)
    if messages:
        text = 'Messages: {}'.format(','.join(messages))
    return web.Response(text=text)


def make_app() -> web.Application:
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
