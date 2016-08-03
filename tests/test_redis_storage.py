import asyncio
import json
import socket
import unittest
import uuid
import aioredis
import time

import pytest

from aiohttp import web, request
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.redis_storage import RedisStorage


@pytest.yield_fixture
def redis(loop):
    pool = None

    @asyncio.coroutine
    def start():
        nonlocal pool
        pool = yield from aioredis.create_pool(('localhost', 6379),
                                               minsize=5,
                                               maxsize=10,
                                               loop=loop)

    loop.run_until_complete(start())
    yield pool
    if pool is not None:
        loop.run_until_complete(pool.clear())


def create_app(loop, handler, redis, max_age=None):
    middleware = session_middleware(
        RedisStorage(redis, max_age=max_age))
    app = web.Application(middlewares=[middleware], loop=loop)
    app.router.add_route('GET', '/', handler)
    return app


@asyncio.coroutine
def make_cookie(client, redis, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    with (yield from redis) as conn:
        yield from conn.set('AIOHTTP_SESSION_' + key, value)
    client.session.cookies['AIOHTTP_SESSION'] = key


@asyncio.coroutine
def load_cookie(client, redis):
    key = client.session.cookies['AIOHTTP_SESSION']
    with (yield from redis) as conn:
        encoded = yield from conn.get('AIOHTTP_SESSION_' + key.value)
        s = encoded.decode('utf-8')
        value = json.loads(s)
        return value


@asyncio.coroutine
def test_create_new_sesssion(test_client, redis):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, redis)
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_load_existing_sesssion(test_client, redis):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, redis)
    yield from make_cookie(client, redis, {'a': 1, 'b': 12})
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_change_sesssion(test_client, redis):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, redis)
    yield from make_cookie(client, redis, {'a': 1, 'b': 2})
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, redis)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'c' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    assert value['session']['c'] == 3
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert '/' == morsel['path']


@asyncio.coroutine
def test_clear_cookie_on_sesssion_invalidation(test_client, redis):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, redis)
    yield from make_cookie(client, redis, {'a': 1, 'b': 2})
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, redis)
    assert {} == value
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert morsel['path'] == '/'


@asyncio.coroutine
def test_create_cookie_in_handler(test_client, redis):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['a'] = 1
        session['b'] = 2
        return web.Response(body=b'OK', headers={'HOST': 'example.com'})

    client = yield from test_client(create_app, handler, redis)
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, redis)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert morsel['path'] == '/'
    with (yield from redis) as conn:
        exists = yield from conn.exists('AIOHTTP_SESSION_' +
                                        morsel.value)
        assert exists


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
            self.loop.run_until_complete(self.srv.wait_closed())
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
    def create_server(self, method, path, handler, max_age=None):
        self.redis = yield from aioredis.create_pool(('localhost', 6379),
                                                     minsize=5,
                                                     maxsize=10,
                                                     loop=self.loop)
        self.addCleanup(self.redis.clear)
        middleware = session_middleware(
            RedisStorage(self.redis, max_age=max_age))
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

    @asyncio.coroutine
    def make_cookie(self, data):
        session_data = {
            'session': data,
            'created': int(time.time())
        }
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
