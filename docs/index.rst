.. aiohttp_session documentation master file, created by
   sphinx-quickstart on Wed Apr  1 21:54:09 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiohttp_session
===============

The library provides sessions for :ref:`aiohttp.web<aiohttp-web>`.

Usage
-----

The library allows to store user-specific data into session object.

The session object has dict-like interface (operations like
``session[key] = value``, ``value = session[key]`` etc. are present).


Before processing session in web-handler you have to register *session
middleware* in ``aiohttp.web.Application``.

A trivial usage example::

    import asycio
    import time
    from aiohttp import web
    import aiohttp_session

    @asyncio.coroutine
    def handler(request):
        session = aiohttp_session.get_session(request)
        session['last_visit'] = time.time()
        return web.Response('OK')

    app = web.Application(middlewares=aiohttp_session.session_middleware(
        aiohttp_session.EncryptedCookieStorage(b'Sixteen byte key')))

    app.router.add_route('GET', '/', handler)

All storages uses HTTP Cookie named ``AIOHTTP_COOKIE_SESSION`` for storing data.

Available session storages are:

* ``aiohttp_session.SimpleCookieStorage()`` -- keeps session data as
  plain JSON string in cookie body. Use the storage only for testing
  purposes, it's very non-secure.

* ``aiohttp_session.cookie_storage.EncryptedCookieStorage(secret_key)``
  -- stores session data into cookies as ``SimpleCookieStorage`` but
  encodes it via AES cipher. ``secrect_key`` is a ``bytes`` key for AES
  encryption/decryption, the length should be 16 bytes.

  Requires ``PyCrypto`` library::

      $ pip install aiohttp_session[pycrypto]

* ``aiohttp_session.redis_storage.RedisStorage(redis_pool)`` -- stores
  JSON-ed data into *redis*, keepeng into cookie only redis key
  (random UUID). ``redis_pool`` is ``aioredis`` pool object, created by
  ``yield from aioredis.create_pool(...)`` call.

  Requires ``aioredis`` library::

      $ pip install aiohttp_session[aioredis]

License
-------

``aiohttp_session`` is offered under the Apache 2 license.

Contents:

.. toctree::
   :maxdepth: 2

   reference
   glossary



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
