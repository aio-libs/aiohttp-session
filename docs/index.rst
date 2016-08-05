.. aiohttp_session documentation master file, created by
   sphinx-quickstart on Wed Apr  1 21:54:09 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiohttp_session
===============

.. currentmodule:: aiohttp_session
.. highlight:: python

The library provides sessions for :ref:`aiohttp.web<aiohttp-web>`.

Usage
-----

The library allows to store user-specific data into session object.

The session object has dict-like interface (operations like
``session[key] = value`` or ``value = session[key]`` etc. are supported).


Before processing session in web-handler you have to register *session
middleware* in :class:`aiohttp.web.Application`.

A trivial usage example::

    import time
    from aiohttp import web
    from aiohttp_session import get_session, setup
    from aiohttp_session.cookie_storage import EncryptedCookieStorage

    async def handler(request):
        session = yield from get_session(request)
        session['last_visit'] = time.time()
        return web.Response(body=b'OK')

    def init():
        app = web.Application()
        setup(app,
            EncryptedCookieStorage(b'Thirty  two  length  bytes  key.'))
        app.router.add_route('GET', '/', handler)
        return app

    web.run_app(init())

All storages uses HTTP Cookie named ``AIOHTTP_COOKIE_SESSION`` for storing data.

Available session storages are:

* :class:`SimpleCookieStorage` -- keeps session data as
  plain JSON string in cookie body. Use the storage only for testing
  purposes, it's very non-secure.

* :class:`~aiohttp_session.cookie_storage.EncryptedCookieStorage`
  -- stores session data into cookies like
  :class:`SimpleCookieStorage` does but
  encodes the data via :term:`cryptography` Fernet cipher.

  For key generation use :meth:`cryptography.fernet.Fernet.generate_key` method.

  Requires :term:`cryptography` library::

      $ pip install aiohttp_session[secure]

* :class:`~aiohttp_session.redis_storage.RedisStorage` -- stores
  JSON-ed data into *redis*, keepeng into cookie only redis key
  (random UUID).

  Requires :term:`aioredis` library::

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


Dependencies
------------

- Python 3.3 and :mod:`asyncio` or Python 3.4+
- :term:`cryptography` for
  :class:`~aiohttp_session.cookie_storage.EncryptedCookieStorage`
- :term:`aioredis` for
  :class:`~aiohttp_session.redis_storage.RedisStorage`.


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
