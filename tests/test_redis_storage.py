import asyncio
import json
import socket
import unittest
import uuid
import aioredis
import time

from aiohttp import web, request
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.redis_storage import RedisStorage


class TestRedisStorage(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.handler = None
        self.srv = None

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
    def create_server(self, method, path, handler=None, max_age=None):
        self.redis = yield from aioredis.create_pool(('localhost', 6379),
                                                     minsize=5,
                                                     maxsize=10,
                                                     loop=self.loop)
        self.addCleanup(self.redis.clear)
        middleware = session_middleware(
            RedisStorage(self.redis, max_age=max_age))
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

    @asyncio.coroutine
    def make_cookie(self, data):
        if data:
            session_data = {
                'session': data,
                'created': int(time.time())
            }
        else:
            session_data = data
        value = json.dumps(session_data)
        key = uuid.uuid4().hex
        with (yield from self.redis) as conn:
            yield from conn.set('AIOHTTP_SESSION_' + key, value)
        return {'AIOHTTP_SESSION': key}

    @asyncio.coroutine
    def load_cookie(self, cookies):
        key = cookies['AIOHTTP_SESSION']
        with (yield from self.redis) as conn:
            encoded = yield from conn.get('AIOHTTP_SESSION_' + key.value)
            s = encoded.decode('utf-8')
            value = json.loads(s)
            return value

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
            cookies = yield from self.make_cookie({'a': 1, 'b': 12})
            resp = yield from request(
                'GET', url,
                cookies=cookies,
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
            cookies = yield from self.make_cookie({'a': 1, 'b': 2})
            resp = yield from request(
                'GET', url,
                cookies=cookies,
                loop=self.loop)
            self.assertEqual(200, resp.status)
            value = yield from self.load_cookie(resp.cookies)
            self.assertIn('session', value)
            self.assertIn('a', value['session'])
            self.assertIn('b', value['session'])
            self.assertIn('c', value['session'])
            self.assertIn('created', value)
            self.assertEqual(value['session']['a'], 1)
            self.assertEqual(value['session']['b'], 2)
            self.assertEqual(value['session']['c'], 3)
            morsel = resp.cookies['AIOHTTP_SESSION']
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
            cookies = yield from self.make_cookie({'a': 1, 'b': 2})
            resp = yield from request(
                'GET', url,
                cookies=cookies,
                loop=self.loop)
            self.assertEqual(200, resp.status)
            value = yield from self.load_cookie(resp.cookies)
            self.assertEqual({}, value)
            morsel = resp.cookies['AIOHTTP_SESSION']
            self.assertTrue(morsel['httponly'])
            self.assertEqual(morsel['path'], '/')

        self.loop.run_until_complete(go())

    def test_create_cookie_in_handler(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            session['a'] = 1
            session['b'] = 2
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            resp = yield from request(
                'GET', url,
                loop=self.loop)
            self.assertEqual(200, resp.status)
            value = yield from self.load_cookie(resp.cookies)
            self.assertIn('session', value)
            self.assertIn('a', value['session'])
            self.assertIn('b', value['session'])
            self.assertIn('created', value)
            self.assertEqual(value['session']['a'], 1)
            self.assertEqual(value['session']['b'], 2)
            morsel = resp.cookies['AIOHTTP_SESSION']
            self.assertTrue(morsel['httponly'])
            self.assertEqual(morsel['path'], '/')
            with (yield from self.redis) as conn:
                exists = yield from conn.exists('AIOHTTP_SESSION_' +
                                                morsel.value)
                self.assertTrue(exists)

        self.loop.run_until_complete(go())

    def test_set_ttl_on_session_saving(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            session['a'] = 1
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler,
                                                      max_age=10)

            resp = yield from request(
                'GET', url,
                loop=self.loop)
            self.assertEqual(200, resp.status)

            key = resp.cookies['AIOHTTP_SESSION'].value

            with (yield from self.redis) as conn:
                ttl = yield from conn.ttl('AIOHTTP_SESSION_'+key)
            self.assertGreater(ttl, 9)
            self.assertLessEqual(ttl, 10)

        self.loop.run_until_complete(go())

    def test_create_new_sesssion_if_key_doesnt_exists_in_redis(self):

        @asyncio.coroutine
        def handler(request):
            session = yield from get_session(request)
            self.assertTrue(session.new)
            return web.Response(body=b'OK')

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server('GET', '/', handler)
            cookies = {'AIOHTTP_SESSION': 'invalid_key'}
            resp = yield from request('GET', url, cookies=cookies,
                                      loop=self.loop)
            self.assertEqual(200, resp.status)

        self.loop.run_until_complete(go())
