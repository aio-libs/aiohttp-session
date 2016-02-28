import asyncio
import bson.json_util as json
from bson import objectid
import socket
import unittest
import time

from aiohttp import web, request
from aiohttp_session import (Session, session_middleware,
                             get_session, SimpleCookieStorage)


class TestSimleCookieStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.srv = None
        self.handler = None
        self.data = {'a': 1, 'b': 2, 'd': objectid.ObjectId()}

    def tearDown(self):
        self.loop.run_until_complete(self.handler.finish_connections())
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
            SimpleCookieStorage(encoder=json.dumps, decoder=json.loads))
        app = web.Application(middlewares=[middleware], loop=self.loop)
        app.router.add_route(method, path, handler)

        port = self.find_unused_port()
        handler = app.make_handler()
        srv = yield from self.loop.create_server(
            handler, '127.0.0.1', port)
        url = "http://127.0.0.1:{}".format(port) + path
        self.handler = handler
        self.srv = srv
        return app, srv, url

    def make_cookie(self):
        session_data = {
            'session': self.data,
            'created': int(time.time())
        }

        value = json.dumps(session_data)
        return {'AIOHTTP_SESSION': value}

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
            self.assertIsNotNone(session.created)
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
            cookies = self.make_cookie()
            resp = yield from request(
                'GET', url,
                cookies=cookies,
                loop=self.loop)
            self.assertEqual(200, resp.status)
            morsel = resp.cookies['AIOHTTP_SESSION']
            cookie_data = json.loads(morsel.value)
            self.assertIn('session', cookie_data)
            self.assertIn('a', cookie_data['session'])
            self.assertIn('b', cookie_data['session'])
            self.assertIn('c', cookie_data['session'])
            self.assertIn('d', cookie_data['session'])
            self.assertIn('e', cookie_data['session'])
            self.assertIn('created', cookie_data)
            self.assertEqual(cookie_data['session']['a'], 1)
            self.assertEqual(cookie_data['session']['b'], 2)
            self.assertEqual(cookie_data['session']['c'], 3)
            self.assertEqual(cookie_data['session']['d'], self.data['d'])
            self.assertEqual(cookie_data['session']['e'], e)
            self.assertTrue(morsel['httponly'])
            self.assertEqual('/', morsel['path'])

        self.loop.run_until_complete(go())

    def test_clear_cookie_on_session_invalidation(self):

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
            self.assertEqual(
                'Set-Cookie: AIOHTTP_SESSION="{}"; httponly; Path=/'.upper(),
                resp.cookies['AIOHTTP_SESSION'].output().upper())

        self.loop.run_until_complete(go())

    def test_dont_save_not_requested_session(self):

        @asyncio.coroutine
        def handler(request):
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                cookies=self.make_cookie(),
                loop=self.loop)
            self.assertEqual(200, resp.status)
            self.assertNotIn('AIOHTTP_SESSION', resp.cookies)

        self.loop.run_until_complete(go())
