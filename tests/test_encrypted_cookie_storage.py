import asyncio
import json
import socket
import unittest
import base64
import time

from Crypto.Cipher import AES
from Crypto import Random

from aiohttp import web, request
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


class TestEncryptedCookieStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.key = b'Sixteen byte key'
        self.handler = None
        self.srv = None

    def tearDown(self):
        if self.handler is not None:
            self.loop.run_until_complete(self.handler.finish_connections())
        if self.srv is not None:
            self.srv.close()
        self.loop.close()

    def find_unused_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    @asyncio.coroutine
    def create_server(self, method, path, handler=None):
        middleware = session_middleware(
            EncryptedCookieStorage(self.key))
        app = web.Application(middlewares=[middleware], loop=self.loop)
        if handler:
            app.router.add_route(method, path, handler)

        port = self.find_unused_port()
        handler = app.make_handler()
        srv = yield from self.loop.create_server(
            handler, '127.0.0.1', port)
        url = "http://127.0.0.1:{}".format(port) + path
        self.srv = srv
        self.handler = handler
        return app, srv, url

    def make_cookie(self, data):
        if data:
            session_data = {
                'session': data,
                'created': int(time.time())
            }
        else:
            session_data = data

        cookie_data = json.dumps(session_data).encode('utf-8')
        if len(cookie_data) % AES.block_size != 0:
            # padding with spaces to full blocks
            to_pad = AES.block_size - (len(cookie_data) % AES.block_size)
            cookie_data += b' ' * to_pad
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(cookie_data)
        encrypted = iv + encrypted
        b64coded = base64.b64encode(encrypted).decode('utf-8')
        return {'AIOHTTP_SESSION': b64coded}

    def decrypt(self, cookie_value):
        assert type(cookie_value) == str
        decoded = base64.b64decode(cookie_value)
        iv = decoded[:AES.block_size]
        data = decoded[AES.block_size:]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(data).decode('utf-8')
        return json.loads(decrypted)

    def test_invalid_key(self):
        with self.assertRaises(TypeError):
            EncryptedCookieStorage(b'123')  # short key

    def test_create_new_sesssion(self):

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
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request('GET', url, loop=self.loop)
            self.assertEqual(200, resp.status)

        self.loop.run_until_complete(go())

    def test_load_existing_sesssion(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            self.assertIsInstance(session, Session)
            self.assertFalse(session.new)
            self.assertFalse(session._changed)
            self.assertEqual({'a': 1, 'b': 12}, session)
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie({'a': 1, 'b': 12}),
                loop=self.loop)
            self.assertEqual(200, resp.status)

        self.loop.run_until_complete(go())

    def test_change_sesssion(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            session['c'] = 3
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie({'a': 1, 'b': 2}),
                loop=self.loop)
            self.assertEqual(200, resp.status)
            morsel = resp.cookies['AIOHTTP_SESSION']
            cookie_data = self.decrypt(morsel.value)
            self.assertIn('session', cookie_data)
            self.assertIn('a', cookie_data['session'])
            self.assertIn('b', cookie_data['session'])
            self.assertIn('c', cookie_data['session'])
            self.assertIn('created', cookie_data)
            self.assertEqual(cookie_data['session']['a'], 1)
            self.assertEqual(cookie_data['session']['b'], 2)
            self.assertEqual(cookie_data['session']['c'], 3)
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
                cookies=self.make_cookie({'a': 1, 'b': 2}),
                loop=self.loop)
            self.assertEqual(200, resp.status)
            morsel = resp.cookies['AIOHTTP_SESSION']
            self.assertEqual('', morsel.value)
            self.assertFalse(morsel['httponly'])
            self.assertEqual(morsel['path'], '/')

        self.loop.run_until_complete(go())
