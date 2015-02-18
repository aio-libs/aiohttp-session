import asyncio
import json
import socket
import unittest

from aiohttp import web, request
from aiohttp_session import (Session, session_middleware,
                             get_session, SimpleCookieStorage)


class TestSimleCookieStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

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
        middleware = session_middleware(SimpleCookieStorage())
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
        value = json.dumps(data)
        return {'AIOHTTP_COOKIE_SESSION': value}

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
            self.assertEqual({'a': 1, 'b': 2}, session)
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie({'a': 1, 'b': 2}),
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
            self.assertEqual({'a': 1, 'b': 2, 'c': 3}, eval(morsel.value))
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
            self.assertEqual(
                'Set-Cookie: AIOHTTP_COOKIE_SESSION="{}"; httponly; Path=/',
                resp.cookies['AIOHTTP_COOKIE_SESSION'].output())

        self.loop.run_until_complete(go())
