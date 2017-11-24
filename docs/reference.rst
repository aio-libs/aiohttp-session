.. _aiohttp-session-reference:


===========
 Reference
===========

.. module:: aiohttp_session
.. currentmodule:: aiohttp_session
.. highlight:: python


Public functions
================

.. function:: get_session(request)

   A :ref:`coroutine<coroutine>` for getting session instance from
   request object.

   See example below in :ref:`Session<aiohttp-session-session>`
   section for :func:`get_session` usage.

.. function:: session_middleware(storage)

   Session middleware factory.

   Create session middleware to pass into
   :class:`aiohttp.web.Application` constructor.

   *storage* is a session storage instance (object used to store
   session data into cookies, Redis, database etc., class is derived
   from :class:`AbstractStorage`).

   .. seealso:: :ref:`aiohttp-session-storage`

   .. note:: :func:`setup` is new-fashion way for library setup.

.. function:: setup(app, storage)

   Setup session support for given *app*.

   The function is shortcut for::

      app.middlewares.append(session_middleware(storage))

   *app* is :class:`aiohttp.web.Application` instance.

   *storage* is a session storage instance (object used to store
   session data into cookies, Redis, database etc., class is derived
   from :class:`AbstractStorage`).

   .. seealso:: :ref:`aiohttp-session-storage`


.. _aiohttp-session-session:

Session
=======

.. class:: Session

   Client's session, a namespace that is valid for some period of
   continual activity that can be used to represent a user's
   interaction with a web application.

   .. warning::

      Never create :class:`Session` instances by hands, retieve those
      by :func:`get_session` call.

   The :class:`Session` is a :class:`MutableMapping`, thus it supports
   all dictionary methods, along with some extra attributes and
   methods::

      from aiohttp_session import get_session

      async def handler(request):
          session = await get_session(request)
          session['key1'] = 'value 1'
          assert 'key2' in session
          assert session['key2'] == 'value 2'
          # ...

   .. attribute:: created

      Creation UNIX TIMESTAMP, the value returned by :func:`time.time`
      for very first access to the session object.

   .. attribute:: identity

      Client's identity. It may be cookie name or database
      key. Read-only property. For change use :func:`Session.set_new_identity`.

   .. attribute:: new

      A boolean. If new is ``True``, this session is new. Otherwise,
      it has been constituted from data that was already serialized.

   .. method:: changed()

      Call this when you mutate a mutable value in the session
      namespace. See the note below for details on when, and why
      you should call this.

      .. note::

         Keys and values of session data must be JSON serializable
         when using one of the included storage backends. This
         means, typically, that they are instances of basic types of
         objects, such as strings, lists, dictionaries, tuples,
         integers, etc. If you place an object in a session data key
         or value that is not JSON serializable, an error will be raised
         when the session is serialized.

         If you place a mutable value (for example, a list or a
         dictionary) in a session object, and you subsequently mutate
         that value, you must call the changed() method of the session
         object. In this case, the session has no way to know that is
         was modified. However, when you modify a session object
         directly, such as setting a value (i.e., ``__setitem__``), or
         removing a key (e.g., ``del`` or ``pop``), the session will
         automatically know that it needs to re-serialize its data,
         thus calling :meth:`changed` is unnecessary. There is no harm
         in calling :meth:`changed` in either case, so when in doubt,
         call it after you've changed sessioning data.

   .. method:: invalidate()

      Call this when you want to invalidate the session (dump all
      data, and -- perhaps -- set a clearing cookie).

   .. method:: set_new_identity(identity)

      Call this when you want to change the :py:attr:`identity`.

      .. warning::

         Never change :py:attr:`identity` of a session which is not new.

.. _aiohttp-session-storage:

Session storages
================

:mod:`aiohttp_session` uses storages to save/load persistend session data.

Abstract Storage
----------------

All storages should be derived from :class:`AbstractStorage` and
implement both :meth:`~AbstractStorage.load_session` and
:meth:`~AbstractStorage.save_session` methods.

.. class:: AbstractStorage(cookie_name="AIOHTTP_SESSION", *, \
                           domain=None, max_age=None, path='/', \
                           secure=None, httponly=True)

   Base class for session storage implementations.

   It uses HTTP cookie for storing at least the key for session data, but
   some implementations may save all session info into cookies.

   *cookie_name* -- name of cookie used for saving session data.

   *domain* -- cookie's domain, :class:`str` or ``None``.

   *max_age* -- cookie's max age, :class:`int` or ``None``.

   *path* -- cookie's path, :class:`str` or ``None``.

   *secure* -- cookie's secure flag, :class:`bool` or ``None`` (the
   same as ``False``).

   *httponly* -- cookie's http-only flag, :class:`bool` or ``None`` (the
   same as ``False``).

   .. attribute:: max_age

      Maximum age for session data, :class:`int` seconds or ``None``
      for "session cookie" which last until you close your browser.

   .. attribute:: cookie_name

      Name of cookie used for saving session data.

   .. attribute:: cookie_params

      :class:`dict` of cookie params: *domain*, *max_age*, *path*,
      *secure* and *httponly*.

   .. method:: load_session(request)

      An *abstract* :ref:`coroutine<coroutine>`, called by internal
      machinery for retrieving :class:`Session` object for given
      *request* (:class:`aiohttp.web.Request` instance).

      Return :class:`Session` instance.

   .. method:: save_session(request, response, session)

      An *abstract* :ref:`coroutine<coroutine>`, called by internal
      machinery for storing *session* (:class:`Session`) instance for
      given *request* (:class:`aiohttp.web.Request`) using *response*
      (:class:`aiohttp.web.StreamResponse` or descendants).

   .. method:: load_cookie(request)

      A helper for loading cookie (:class:`http.cookies.SimpleCookie`
      instance) from *request* (:class:`aiohttp.web.Request`).

   .. method:: save_cookie(response, cookie_data, *, max_age=None)

      A helper for saving *cookie_data* (:class:`str`) into *response*
      (:class:`aiohttp.web.StreamResponse` or descendants).

      *max_age* is cookie lifetime given from session. Storage defailt
      is used if the value is ``None``.


Simple Storage
--------------

For testing purposes there is :class:`SimpleCookieStorage`. It stores
session data as unencrypted and unsigned JSON data in browser cookies,
so it's totally insecure.

.. warning:: Never use this storage on production!!! It's highly insecure!!!

To use the storage you should push it into
:func:`session_middleware`::

   aiohttp_session.setup(app, aiohttp_session.SimpleCookieStorage())

.. class:: SimpleCookieStorage(*, \
                               cookie_name="AIOHTTP_SESSION", \
                               domain=None, max_age=None, path='/', \
                               secure=None, httponly=True)

   Create unencrypted cookie storage.

   The class is inherited from :class:`AbstractStorage`.

   Parameters are the same as for :class:`AbstractStorage`
   constructor.


.. module:: aiohttp_session.cookie_storage
.. currentmodule:: aiohttp_session.cookie_storage


Cookie Storage
--------------

The storage that saves session data in HTTP cookies as
:class:`~cryptography.fernet.Fernet` encrypted data.

To use the storage you should push it into
:func:`~aiohttp_session.session_middleware`::

   app = aiohttp.web.Application(middlewares=[
       aiohttp_session.cookie_storage.EncryptedCookieStorage(
           b'Thirty  two  length  bytes  key.'])

.. class:: EncryptedCookieStorage(secret_key, *, \
                                  cookie_name="AIOHTTP_SESSION", \
                                  domain=None, max_age=None, path='/', \
                                  secure=None, httponly=True)

   Create encryted cookies storage.

   The class is inherited from :class:`~aiohttp_session.AbstractStorage`.

   *secret_key* is :class:`bytes` secret key with length of 32, used
   for encoding or base-64 encoded :class:`str` one.

   Other parameters are the same as for
   :class:`~aiohttp_session.AbstractStorage` constructor.

   .. note::

      For key generation use
      :meth:`cryptography.fernet.Fernet.generate_key` method.


.. module:: aiohttp_session.cookie_storage
.. currentmodule:: aiohttp_session.cookie_storage


NaCl Storage
--------------

The storage that saves session data in HTTP cookies as
:class:`~nacl.secret.SecretBox` encrypted data.

To use the storage you should push it into
:func:`~aiohttp_session.session_middleware`::

   app = aiohttp.web.Application(middlewares=[
       aiohttp_session.cookie_storage.NaClCookieStorage(
           b'Thirty  two  length  bytes  key.'])

.. class:: NaClCookieStorage(secret_key, *, \
                                  cookie_name="AIOHTTP_SESSION", \
                                  domain=None, max_age=None, path='/', \
                                  secure=None, httponly=True)

   Create encryted cookies storage.

   The class is inherited from :class:`~aiohttp_session.AbstractStorage`.

   *secret_key* is :class:`bytes` secret key with length of 32, used
   for encoding.

   Other parameters are the same as for
   :class:`~aiohttp_session.AbstractStorage` constructor.


.. module:: aiohttp_session.redis_storage
.. currentmodule:: aiohttp_session.redis_storage


Redis Storage
-------------

The storage that stores session data in Redis database and
keeps only Redis keys (UUIDs actually) in HTTP cookies.

It operates with Redis database via :class:`aioredis.RedisPool`.

To use the storage you need setup it first::

   redis = await aioredis.create_pool(('localhost', 6379))
   storage = aiohttp_session.redis_storage.RedisStorage(redis)
   aiohttp_session.setup(app, storage)


.. class:: RedisStorage(redis_pool, *, \
                        cookie_name="AIOHTTP_SESSION", \
                        domain=None, max_age=None, path='/', \
                        secure=None, httponly=True, \
                        encoder=json.dumps, \
                        decoder=json.loads, \
                        key_factory=lambda: uuid.uuid4().hex)

   Create Redis storage for user session data.

   The class is inherited from :class:`~aiohttp_session.AbstractStorage`.

   *redis_pool* is a :class:`~aioredis.RedisPool` which should be
   created by :func:`~aioredis.create_pool` call, e.g.::

      redis = await aioredis.create_pool(('localhost', 6379))
      storage = aiohttp_session.redis_storage.RedisStorage(redis)

   Other parameters are the same as for
   :class:`~aiohttp_session.AbstractStorage` constructor.


Memcahed Storage
----------------

The storage that stores session data in Memcached and
keeps only keys (UUIDs actually) in HTTP cookies.

It operates with Memcahed database via :class:`aiomecache.Client`.

To use the storage you need setup it first::

   mc = aiomchache.Client('localhost', 11211)
   storage = aiohttp_session.memcached_storage.Client(mc)
   aiohttp_session.setup(app, storage)

.. versionadded:: 1.2

.. class:: MemcachedStorage(memcached_conn, *, \
                            cookie_name="AIOHTTP_SESSION", \
                            domain=None, max_age=None, path='/', \
                            secure=None, httponly=True, \
                            encoder=json.dumps, \
                            decoder=json.loads, \
                            key_factory=lambda: uuid.uuid4().hex)

   Create Memcached storage for user session data.

   The class is inherited from :class:`~aiohttp_session.AbstractStorage`.

   *memcached_conn* is a :class:`~aiomcache.Client` instance::

      mc = await aiomcache.Client('localhost', 6379)
      storage = aiohttp_session.memcached_storage.MemcachedStorage(mc

   Other parameters are the same as for
   :class:`~aiohttp_session.AbstractStorage` constructor.
