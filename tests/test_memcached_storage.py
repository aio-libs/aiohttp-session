import asyncio
import json
import uuid
import aiomcache
import time
import pytest

from aiohttp import web
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.memcached_storage import MemcachedStorage


@pytest.yield_fixture
def memcached(loop):
    conn = aiomcache.Client("127.0.0.1", 11211, loop=loop)
    yield conn
    conn.close()


def create_app(loop, handler, memcached, max_age=None,
               key_factory=lambda: uuid.uuid4().hex):
    middleware = session_middleware(
        MemcachedStorage(memcached, max_age=max_age, key_factory=key_factory))
    app = web.Application(middlewares=[middleware], loop=loop)
    app.router.add_route('GET', '/', handler)
    return app


@asyncio.coroutine
def make_cookie(client, memcached, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    storage_key = ('AIOHTTP_SESSION_' + key).encode('utf-8')
    yield from memcached.set(storage_key, bytes(value, 'utf-8'))
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


@asyncio.coroutine
def make_cookie_with_bad_value(client, memcached):
    key = uuid.uuid4().hex
    storage_key = ('AIOHTTP_SESSION_' + key).encode('utf-8')
    yield from memcached.set(storage_key, b'')
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


@asyncio.coroutine
def load_cookie(client, memcached):
    cookies = client.session.cookie_jar.filter_cookies(client.make_url('/'))
    key = cookies['AIOHTTP_SESSION']
    storage_key = ('AIOHTTP_SESSION_' + key.value).encode('utf-8')
    encoded = yield from memcached.get(storage_key)
    s = encoded.decode('utf-8')
    value = json.loads(s)
    return value


@asyncio.coroutine
def test_create_new_sesssion(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_load_existing_sesssion(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    yield from make_cookie(client, memcached, {'a': 1, 'b': 12})
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_load_bad_sesssion(test_client, memcached):
    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    yield from make_cookie_with_bad_value(client, memcached)
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_change_sesssion(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    yield from make_cookie(client, memcached, {'a': 1, 'b': 2})
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, memcached)
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
def test_clear_cookie_on_sesssion_invalidation(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    yield from make_cookie(client, memcached, {'a': 1, 'b': 2})
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, memcached)
    assert {} == value
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['path'] == '/'
    assert morsel['expires'] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel['max-age'] == "0"


@asyncio.coroutine
def test_create_cookie_in_handler(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['a'] = 1
        session['b'] = 2
        return web.Response(body=b'OK', headers={'HOST': 'example.com'})

    client = yield from test_client(create_app, handler, memcached)
    resp = yield from client.get('/')
    assert resp.status == 200

    value = yield from load_cookie(client, memcached)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert morsel['path'] == '/'
    storage_key = ('AIOHTTP_SESSION_' + morsel.value).encode('utf-8')
    exists = yield from memcached.get(storage_key)
    assert exists


@asyncio.coroutine
def test_create_new_sesssion_if_key_doesnt_exists_in_memcached(
        test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        assert session.new
        return web.Response(body=b'OK')

    client = yield from test_client(create_app, handler, memcached)
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': 'invalid_key'})
    resp = yield from client.get('/')
    assert resp.status == 200


@asyncio.coroutine
def test_create_storate_with_custom_key_factory(test_client, memcached):

    @asyncio.coroutine
    def handler(request):
        session = yield from get_session(request)
        session['key'] = 'value'
        assert session.new
        return web.Response(body=b'OK')

    def key_factory():
        return 'test-key'

    client = yield from test_client(create_app, handler, memcached, 8,
                                    key_factory)
    resp = yield from client.get('/')
    assert resp.status == 200

    assert resp.cookies['AIOHTTP_SESSION'].value == 'test-key'

    value = yield from load_cookie(client, memcached)
    assert 'key' in value['session']
    assert value['session']['key'] == 'value'
