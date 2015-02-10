import asyncio
import json
import socket
import unittest
import base64

from Crypto.Cipher import AES

from aiohttp import web, request
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


class TestSimleCookieStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.key = b'Sixteen byte key'
        self.iv = b'This is an IV456'

    def tearDown(self):
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
            EncryptedCookieStorage(self.key, iv=self.iv))
        app = web.Application(middlewares=[middleware], loop=self.loop)
        if handler:
            app.router.add_route(method, path, handler)

        port = self.find_unused_port()
        srv = yield from self.loop.create_server(
            app.make_handler(), '127.0.0.1', port)
        url = "http://127.0.0.1:{}".format(port) + path
        self.addCleanup(srv.close)
        return app, srv, url

    def make_cookie(self, data):
        cookie_data = json.dumps(data).encode('utf-8')
        if len(cookie_data) % AES.block_size != 0:
            # padding with spaces to full blocks
            to_pad = AES.block_size - (len(cookie_data) % AES.block_size)
            cookie_data += b' ' * to_pad
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = cipher.encrypt(cookie_data)
        b64coded = base64.b64encode(encrypted).decode('utf-8')
        return {'AIOHTTP_COOKIE_SESSION': b64coded}

    def test_init(self):
        EncryptedCookieStorage(self.key)  # ensure that random IV do not fail
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
            morsel = resp.cookies['AIOHTTP_COOKIE_SESSION']
            cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
            decoded = base64.b64decode(morsel.value)
            decrypted = cipher.decrypt(decoded).decode('utf-8')
            self.assertEqual({'a': 1, 'b': 2, 'c': 3}, json.loads(decrypted))
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
            cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
            encrypted = cipher.encrypt('{}'+' '*14)
            b64coded = base64.b64encode(encrypted).decode('utf-8')
            expected_header = ('Set-Cookie: AIOHTTP_COOKIE_SESSION="{}"; '
                               'httponly; Path=/').format(b64coded)
            self.assertEqual(expected_header,
                             resp.cookies['AIOHTTP_COOKIE_SESSION'].output())

        self.loop.run_until_complete(go())
