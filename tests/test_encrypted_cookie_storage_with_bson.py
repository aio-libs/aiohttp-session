import asyncio
from bson import json_util as json
from bson import objectid
import socket
import unittest
import base64
import time

from aiohttp import web, request

from cryptography import fernet

from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


class TestEncryptedCookieStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

        key = fernet.Fernet.generate_key()
        self.fernet = fernet.Fernet(key)
        self.key = base64.urlsafe_b64decode(key)
        self.handler = None
        self.srv = None
        self.data = {'a': 1, 'b': 12, 'd': objectid.ObjectId()}

    def tearDown(self):
        if self.handler is not None:
            self.loop.run_until_complete(self.handler.finish_connections())
        if self.srv is not None:
            self.srv.close()
        self.loop.stop()
        self.loop.run_forever()
        self.loop.close()

    def find_unused_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    @asyncio.coroutine
    def create_server(self, method, path, handler):
        middleware = session_middleware(
            EncryptedCookieStorage(self.key,
                                   encoder=json.dumps,
                                   decoder=json.loads))
        app = web.Application(middlewares=[middleware], loop=self.loop)
        app.router.add_route(method, path, handler)

        port = self.find_unused_port()
        handler = app.make_handler()
        srv = yield from self.loop.create_server(
            handler, '127.0.0.1', port)
        url = "http://127.0.0.1:{}".format(port) + path
        self.srv = srv
        self.handler = handler
        return app, srv, url

    def make_cookie(self):
        session_data = {
            'session': self.data,
            'created': int(time.time())
        }

        cookie_data = json.dumps(session_data).encode('utf-8')
        data = self.fernet.encrypt(cookie_data).decode('utf-8')

        return {'AIOHTTP_SESSION': data}

    def decrypt(self, cookie_value):
        assert type(cookie_value) == str
        return json.loads(
            self.fernet.decrypt(cookie_value.encode('utf-8')).decode('utf-8')
        )

    def test_invalid_key(self):
        with self.assertRaises(ValueError):
            EncryptedCookieStorage(b'123')  # short key

    def test_create_new_sesssion_broken_by_fermat(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            self.assertIsInstance(session, Session)
            self.assertTrue(session.new)
            self.assertFalse(session._changed)
            self.assertEqual({}, session)
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            key = fernet.Fernet.generate_key()
            self.key = base64.urlsafe_b64decode(key)

            _, _, url = yield from self.create_server(
                'GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie(),
                loop=self.loop)
            self.assertEqual(200, resp.status)

        self.loop.run_until_complete(go())

    def test_load_existing_sesssion(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            self.assertIsInstance(session, Session)
            self.assertFalse(session.new)
            self.assertFalse(session._changed)
            self.assertEqual(self.data, session)
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie(),
                loop=self.loop)
            self.assertEqual(200, resp.status)

        self.loop.run_until_complete(go())

    def test_change_sesssion(self):
        e = objectid.ObjectId()

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            session['c'] = 3
            session['e'] = e
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie(),
                loop=self.loop)
            self.assertEqual(200, resp.status)
            morsel = resp.cookies['AIOHTTP_SESSION']
            cookie_data = self.decrypt(morsel.value)
            self.assertIn('session', cookie_data)
            self.assertIn('a', cookie_data['session'])
            self.assertIn('b', cookie_data['session'])
            self.assertIn('c', cookie_data['session'])
            self.assertIn('d', cookie_data['session'])
            self.assertIn('e', cookie_data['session'])
            self.assertIn('created', cookie_data)
            self.assertEqual(cookie_data['session']['a'], 1)
            self.assertEqual(cookie_data['session']['b'], 12)
            self.assertEqual(cookie_data['session']['c'], 3)
            self.assertEqual(cookie_data['session']['d'], self.data['d'])
            self.assertEqual(cookie_data['session']['e'], e)
            self.assertTrue(morsel['httponly'])
            self.assertEqual('/', morsel['path'])

        self.loop.run_until_complete(go())

    def test_clear_cookie_on_sesssion_invalidation(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            session.invalidate()
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie(),
                loop=self.loop)
            self.assertEqual(200, resp.status)
            morsel = resp.cookies['AIOHTTP_SESSION']
            self.assertEqual('', morsel.value)
            self.assertFalse(morsel['httponly'])
            self.assertEqual(morsel['path'], '/')

        self.loop.run_until_complete(go())
