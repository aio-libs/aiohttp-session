.. _aiohttp-session-reference:


===========
 Reference
===========

.. module:: aiohttp_session
.. currentmodule:: aiohttp_session


Public functions
================

.. function:: get_session(request)

   A :ref:`coroutine<coroutine>` for getting session instance from
   request object.

   See example below in :ref:`Session<aiohttp-session-session>`
   section for :func:`get_session` usage.


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

      @asyncio.coroutine
      def handler(request):
          session = yield from get_session(request)
          session['key1'] = 'value 1'
          assert 'key2' in session
          assert session['key2'] == 'value 2'
          # ...

   .. attribute:: created

      TIMESTAMP

   .. attribute:: identity

      Client's identity. It may be cookie name or database
      key. Read-only property.

   .. attribute:: new

      A boolean. If new is ``True``, this session is new. Otherwise,
      it has been constituted from data that was already serialized.

   .. method:: changed()

      Call this when you mutate a mutable value in the session
      namespace. See the note below for details on when, and why
      you should call this.

      .. note::

         Keys and values of session data must be pickleable. This
         means, typically, that they are instances of basic types of
         objects, such as strings, lists, dictionaries, tuples,
         integers, etc. If you place an object in a session data key
         or value that is not pickleable, an error will be raised when
         the session is serialized.

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
