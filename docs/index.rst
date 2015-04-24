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

    import asyncio
    import time
    from aiohttp import web
    from aiohttp_session import get_session, session_middleware
    from aiohttp_session.cookie_storage import EncryptedCookieStorage

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['last_visit'] = time.time()
        return web.Response(body=b'OK')

    @asyncio.coroutine
    def init(loop):
        app = web.Application(middlewares=[session_middleware(
            EncryptedCookieStorage(b'Sixteen byte key'))])
        app.router.add_route('GET', '/', handler)
        srv = yield from loop.create_server(
            app.make_handler(), '0.0.0.0', 8080)
        return srv

    loop = asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

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

Installation
--------------------

.. code::

   pip3 install aiohttp_session

Source code
-----------

The project is hosted on GitHub_

.. _GitHub: https://github.com/aio-libs/aiohttp_session

Please feel free to file an issue on `bug tracker
<https://github.com/aio-libs/aiopg/issues>`_ if you have found a bug
or have some suggestion for library improvement.

The library uses `Travis <https://travis-ci.org/aio-libs/aiohttp_session>`_ for
Continious Integration.

IRC channel
-----------

You can discuss the library on Freenode_ at **#aio-libs** channel.

.. _Freenode: http://freenode.net


Dependencies
------------

- Python 3.3 and :mod:`asyncio` or Python 3.4+
- psycopg2
- aiopg.sa requires :term:`sqlalchemy`.


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
