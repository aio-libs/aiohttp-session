aiohttp_session
===============

The library provides sessions for `aiohttp.web`__.

.. _aiohttp_web: https://aiohttp.readthedocs.io/en/latest/web.html

__ aiohttp_web_

Usage
-----

The library allows to store user-specific data into session object.

The session object has dict-like interface (operations like
``session[key] = value``, ``value = session[key]`` etc. are present).


Before processing session in web-handler you have to register *session
middleware* in ``aiohttp.web.Application``.

A trivial usage example::

    import asyncio
    import time
    import base64
    from cryptography import fernet
    from aiohttp import web
    from aiohttp_session import setup, get_session, session_middleware
    from aiohttp_session.cookie_storage import EncryptedCookieStorage

    async def handler(request):
        session = await get_session(request)
        last_visit = session['last_visit'] if 'last_visit' in session else None
        text = 'Last visited: {}'.format(last_visit)
        return web.Response(body=text.encode('utf-8'))

    def make_app():
        app = web.Application()
        # secret_key must be 32 url-safe base64-encoded bytes
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(app, EncryptedCookieStorage(secret_key))
        app.router.add_route('GET', '/', handler)
        return app

    web.run_app(make_app())


All storages uses HTTP Cookie named ``AIOHTTP_COOKIE_SESSION`` for storing data.

Available session storages are:

* ``aiohttp_session.SimpleCookieStorage()`` -- keeps session data as
  plain JSON string in cookie body. Use the storage only for testing
  purposes, it's very non-secure.

* ``aiohttp_session.cookie_storage.EncryptedCookieStorage(secret_key)``
  -- stores session data into cookies as ``SimpleCookieStorage`` but
  encodes it via AES cipher. ``secrect_key`` is a ``bytes`` key for AES
  encryption/decryption, the length should be 32 bytes.

  Requires ``cryptography`` library::

      $ pip install aiohttp_session[secure]

* ``aiohttp_session.redis_storage.RedisStorage(redis_pool)`` -- stores
  JSON-ed data into *redis*, keepeng into cookie only redis key
  (random UUID). ``redis_pool`` is ``aioredis`` pool object, created by
  ``yield from aioredis.create_pool(...)`` call.

  Requires ``aioredis`` library::

      $ pip install aiohttp_session[aioredis]

License
-------

``aiohttp_session`` is offered under the Apache 2 license.
