import aioredis
import json
import pytest
import uuid
import time
import asyncio

from aiohttp import web
from aiohttp_session import Session, session_middleware, get_session
from aiohttp_session.redis_storage import RedisStorage


def create_app(handler, redis, max_age=None,
               key_factory=lambda: uuid.uuid4().hex):
    middleware = session_middleware(
        RedisStorage(redis, max_age=max_age, key_factory=key_factory))
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


async def make_cookie(client, redis, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    with await redis as conn:
        await conn.set('AIOHTTP_SESSION_' + key, value)
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def make_cookie_with_bad_value(client, redis):
    key = uuid.uuid4().hex
    with await redis as conn:
        await conn.set('AIOHTTP_SESSION_' + key, '')
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def load_cookie(client, redis):
    cookies = client.session.cookie_jar.filter_cookies(client.make_url('/'))
    key = cookies['AIOHTTP_SESSION']
    with await redis as conn:
        encoded = await conn.get('AIOHTTP_SESSION_' + key.value)
        s = encoded.decode('utf-8')
        value = json.loads(s)
        return value


async def test_create_new_session(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_bad_session(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie_with_bad_value(client, redis)
    resp = await client.get('/')
    assert resp.status == 200


async def test_change_session(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, redis)
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


async def test_clear_cookie_on_session_invalidation(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, redis)
    assert {} == value
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['path'] == '/'
    assert morsel['expires'] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel['max-age'] == "0"


async def test_create_cookie_in_handler(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        session['b'] = 2
        return web.Response(body=b'OK', headers={'HOST': 'example.com'})

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, redis)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert morsel['path'] == '/'
    with await redis as conn:
        exists = await conn.exists('AIOHTTP_SESSION_' + morsel.value)
        assert exists


async def test_set_ttl_on_session_saving(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis, max_age=10))
    resp = await client.get('/')
    assert resp.status == 200

    key = resp.cookies['AIOHTTP_SESSION'].value

    with await redis as conn:
        ttl = await conn.ttl('AIOHTTP_SESSION_'+key)

    assert ttl > 9
    assert ttl <= 10


async def test_set_ttl_manually_set(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session.max_age = 10
        session['a'] = 1
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get('/')
    assert resp.status == 200

    key = resp.cookies['AIOHTTP_SESSION'].value

    with await redis as conn:
        ttl = await conn.ttl('AIOHTTP_SESSION_'+key)

    assert ttl > 9
    assert ttl <= 10


async def test_create_new_session_if_key_doesnt_exists_in_redis(
        aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        assert session.new
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, redis))
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': 'invalid_key'})
    resp = await client.get('/')
    assert resp.status == 200


async def test_create_storage_with_custom_key_factory(aiohttp_client, redis):

    async def handler(request):
        session = await get_session(request)
        session['key'] = 'value'
        assert session.new
        return web.Response(body=b'OK')

    def key_factory():
        return 'test-key'

    client = await aiohttp_client(create_app(handler, redis, 8, key_factory))
    resp = await client.get('/')
    assert resp.status == 200

    assert resp.cookies['AIOHTTP_SESSION'].value == 'test-key'

    value = await load_cookie(client, redis)
    assert 'key' in value['session']
    assert value['session']['key'] == 'value'


async def test_redis_session_fixation(aiohttp_client, redis):
    async def login(request):
        session = await get_session(request)
        session['k'] = 'v'
        return web.Response()

    async def logout(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response()

    app = create_app(login, redis)
    app.router.add_route('DELETE', '/', logout)
    client = await aiohttp_client(app)
    resp = await client.get('/')
    assert 'AIOHTTP_SESSION' in resp.cookies
    evil_cookie = resp.cookies['AIOHTTP_SESSION'].value
    resp = await client.delete('/')
    assert resp.cookies['AIOHTTP_SESSION'].value == ""
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': evil_cookie})
    resp = await client.get('/')
    assert resp.cookies['AIOHTTP_SESSION'].value != evil_cookie


async def test_redis_from_create_pool(redis_params):

    async def handler(request):
        pass

    redis = await aioredis.create_pool(**redis_params)
    with pytest.warns(DeprecationWarning):
        create_app(handler=handler, redis=redis)


async def test_not_redis_provided_to_storage():

    async def handler(request):
        pass

    with pytest.raises(TypeError):
        create_app(handler=handler, redis=None)


async def test_no_aioredis_installed(mocker):

    async def handler(request):
        pass

    mocker.patch('aiohttp_session.redis_storage.aioredis', None)
    with pytest.raises(RuntimeError):
        create_app(handler=handler, redis=None)


async def test_old_aioredis_version(mocker):

    async def handler(request):
        pass

    class Dummy(object):
        def __init__(self, *args, **kwargs):
            self.version = (0, 3)

    mocker.patch('aiohttp_session.redis_storage.StrictVersion', Dummy)
    with pytest.raises(RuntimeError):
        create_app(handler=handler, redis=None)


async def test_load_session_dont_load_expired_session(aiohttp_client,
                                                      redis):
    async def handler(request):
        session = await get_session(request)
        exp_param = request.rel_url.query.get('exp', None)
        if exp_param is None:
            session['a'] = 1
            session['b'] = 2
        else:
            assert {} == session

        return web.Response(body=b'OK')

    client = await aiohttp_client(
        create_app(handler, redis, 2)
    )
    resp = await client.get('/')
    assert resp.status == 200

    await asyncio.sleep(5)

    resp = await client.get('/?exp=yes')
    assert resp.status == 200
