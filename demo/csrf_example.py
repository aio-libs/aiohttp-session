import base64

from cryptography import fernet
from aiohttp import web
from aiohttp import hdrs
from aiohttp_session import setup, generate_csrf_token, check_csrf_token
from aiohttp_session.cookie_storage import EncryptedCookieStorage


tmpl = '''\
<html>
    <body>
        <form action="" method="POST">
            <input type="hidden"
                   name="csrf_token" value="{csrf_token}" />
            <input type="submit" name="submit" value="Do Dangerous Things" />
        </form>
    </body>
</html>'''


async def handler(request):
    if request.method == hdrs.METH_GET:
        csrf_token = await generate_csrf_token(request)
        text = tmpl.format(csrf_token=csrf_token)
        return web.Response(content_type='text/html', text=text)
    elif request.method == hdrs.METH_POST:
        # token keyword argument is the name of the input on your form
        csrf_check = await check_csrf_token(request, token='csrf_token')
        if not csrf_check:
            raise web.HTTPBadRequest(text='Bad CSRF token')
        else:
            return web.Response(text='Dangerous action has been performed!')
    else:
        return web.HTTPMethodNotAllowed(
            method=request.method,
            allowed_methods=(hdrs.METH_GET, hdrs.METH_POST),
        )


def make_app():
    app = web.Application()
    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))
    app.router.add_route('*', '/', handler)
    return app


web.run_app(make_app())

