import base64
from http import HTTPStatus

from cryptography import fernet
from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


DATABASE = [
    ('admin', 'admin'),
]


def login_required(fn):
    async def wrapped(request, *args, **kwargs):
        app = request.app
        router = app.router

        session = await get_session(request)

        if 'user_id' not in session:
            return web.HTTPFound(router['login'].url_for())

        user_id = session['user_id']
        # actually load user from your database (e.g. with aiopg)
        user = DATABASE[user_id]
        app['user'] = user
        return await fn(request, *args, **kwargs)

    return wrapped


@login_required
async def handler(request):
    user = request.app['user']
    return web.Response(text='User {} authorized'.format(user))


tmpl = '''\
<html>
    <body>
        <form method="post" action="login">
            <label>Name:</label><input type="text" name="name"/>
            <label>Password:</label><input type="password" name="password"/>
            <input type="submit" value="Login"/>
        </form>
    </body>
</html>'''


async def login_page(request):
    return web.Response(content_type='text/html', text=tmpl)


async def login(request):
    router = request.app.router
    form = await request.post()
    user_signature = (form['name'], form['password'])

    # actually implement business logic to check user credentials
    try:
        user_id = DATABASE.index(user_signature)
        session = await get_session(request)
        session['user_id'] = user_id
        return web.HTTPFound(router['restricted'].url_for())
    except ValueError:
        return web.Response(text='No such user', status=HTTPStatus.FORBIDDEN)


def make_app():
    app = web.Application()
    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))
    app.router.add_get('/', handler, name='restricted')
    app.router.add_get('/login', login_page, name='login')
    app.router.add_post('/login', login)
    return app


web.run_app(make_app())
