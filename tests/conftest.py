import aiomcache
import aioredis
import asyncio
import gc
import pytest
import time
import uuid
from docker import Client as DockerClient


@pytest.fixture(scope='session')
def loop(request):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)

    yield loop

    if not loop._closed:
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()
    gc.collect()
    asyncio.set_event_loop(None)


@pytest.fixture(scope='session')
def session_id():
    """Unique session identifier, random string."""
    return str(uuid.uuid4())


@pytest.fixture(scope='session')
def docker():
    return DockerClient(version='auto')


def pytest_addoption(parser):
    parser.addoption("--no-pull", action="store_true", default=False,
                     help="Don't perform docker images pulling")


@pytest.fixture(scope='session')
def redis_server(docker, session_id, loop, request):
    if not request.config.option.no_pull:
        docker.pull('redis:{}'.format('latest'))
    container = docker.create_container(
        image='redis:{}'.format('latest'),
        name='redis-test-server-{}-{}'.format('latest', session_id),
        ports=[6379],
        detach=True,
    )
    docker.start(container=container['Id'])
    inspection = docker.inspect_container(container['Id'])
    host = inspection['NetworkSettings']['IPAddress']
    delay = 0.001
    for i in range(100):
        try:
            conn = loop.run_until_complete(
                aioredis.create_connection((host, 6379), loop=loop)
            )
            loop.run_until_complete(conn.execute('SET', 'foo', 'bar'))
            break
        except ConnectionRefusedError as e:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start redis server")
    container['redis_params'] = dict(address=(host, 6379))
    yield container

    docker.kill(container=container['Id'])
    docker.remove_container(container['Id'])


@pytest.fixture
def redis_params(redis_server):
    return dict(**redis_server['redis_params'])


@pytest.fixture
def redis(loop, redis_params):
    pool = None

    async def start(*args, no_loop=False, **kwargs):
        nonlocal pool
        params = redis_params.copy()
        params.update(kwargs)
        useloop = None if no_loop else loop
        pool = await aioredis.create_redis_pool(loop=useloop, **params)
        return pool

    loop.run_until_complete(start())
    yield pool
    if pool is not None:
        pool.close()
        loop.run_until_complete(pool.wait_closed())


@pytest.fixture(scope='session')
def memcached_server(docker, session_id, loop, request):
    if not request.config.option.no_pull:
        docker.pull('memcached:{}'.format('latest'))
    container = docker.create_container(
        image='memcached:{}'.format('latest'),
        name='memcached-test-server-{}-{}'.format('latest', session_id),
        ports=[11211],
        detach=True,
    )
    docker.start(container=container['Id'])
    inspection = docker.inspect_container(container['Id'])
    host = inspection['NetworkSettings']['IPAddress']
    delay = 0.001
    for i in range(100):
        try:
            conn = aiomcache.Client(host, 11211, loop=loop)
            loop.run_until_complete(conn.set(b'foo', b'bar'))
            break
        except ConnectionRefusedError as e:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start memcached server")
    container['memcached_params'] = dict(host=host, port=11211)
    yield container

    docker.kill(container=container['Id'])
    docker.remove_container(container['Id'])


@pytest.fixture
def memcached_params(memcached_server):
    return dict(**memcached_server['memcached_params'])


@pytest.fixture
def memcached(loop, memcached_params):
    conn = aiomcache.Client(loop=loop, **memcached_params)
    yield conn
    conn.close()
