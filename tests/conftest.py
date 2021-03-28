import aiomcache
import aioredis
import asyncio
import gc
import pytest
import sys
import time
import uuid
from docker import (
    DockerClient,
    models as docker_models,
    from_env as docker_from_env
)
import socket

from typing import Any, Generator, Tuple
if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

_TContainerInfo = TypedDict(
    '_TContainerInfo',
    {
        'host': str,
        'port': int,
        'container': docker_models.containers.Container,
    },
)


_TRedisParams = TypedDict(
    '_TRedisParams',
    {
        'address': Tuple[str, int]
    },
)

_TMemcachedParams = TypedDict(
    '_TMemcachedParams',
    {
        'host': str,
        'port': int,
    },
)


def unused_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port: int = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope='session')
def loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)

    yield loop

    if not loop.is_closed():
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()
    gc.collect()
    asyncio.set_event_loop(None)


@pytest.fixture(scope='session')
def session_id() -> str:
    """Unique session identifier, random string."""
    return str(uuid.uuid4())


@pytest.fixture(scope='session')
def docker() -> DockerClient:
    client = docker_from_env(version='auto')
    return client


@pytest.fixture(scope='session')
def redis_server(
    docker: DockerClient,
    session_id: str,
    loop: asyncio.AbstractEventLoop,
) -> Generator[_TContainerInfo, None, None]:

    image = 'redis:{}'.format('latest')

    if sys.platform.startswith('darwin'):
        port = unused_port()
    else:
        port = None

    container = docker.containers.run(
        image=image,
        detach=True,
        name='redis-test-server-{}-{}'.format('latest', session_id),
        ports={
            '6379/tcp': port,
        },
        environment={
            'http.host': '0.0.0.0',
            'transport.host': '127.0.0.1',
        },
    )

    if sys.platform.startswith('darwin'):
        host = '0.0.0.0'
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection['NetworkSettings']['IPAddress']
        port = 6379

    delay = 0.1
    for i in range(20):
        try:
            conn = loop.run_until_complete(
                aioredis.create_connection((host, port), loop=loop)
            )
            loop.run_until_complete(conn.execute('SET', 'foo', 'bar'))
            break
        except ConnectionRefusedError:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start redis server")

    yield {'host': host,
           'port': port,
           'container': container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def redis_params(redis_server: _TContainerInfo) -> _TRedisParams:
    return dict(address=(redis_server['host'], redis_server['port']))


@pytest.fixture
def redis(
    loop: asyncio.AbstractEventLoop,
    redis_params: _TRedisParams,
) -> Generator[aioredis.commands.Redis, None, None]:
    pool = None

    async def start(
        *args: Tuple[Any, ...],
        no_loop: bool = False,
        **kwargs: Any,
    ) -> aioredis.commands.Redis:
        nonlocal pool
        params = redis_params.copy()
        # Ignoring type as this is an unused option to pass arbitrary arguments
        # when creating a redis connection. Alternative: create the typing for
        # `aioredis.create_redis_pool` ourselves.
        params.update(kwargs)  # type: ignore[arg-type]
        useloop = None if no_loop else loop
        pool = await aioredis.create_redis_pool(loop=useloop, **params)
        return pool

    loop.run_until_complete(start())
    yield pool
    if pool is not None:
        pool.close()
        loop.run_until_complete(pool.wait_closed())


@pytest.fixture(scope='session')
def memcached_server(
    docker: DockerClient,
    session_id: str, loop: asyncio.AbstractEventLoop,
) -> Generator[_TContainerInfo, None, None]:

    image = 'memcached:{}'.format('latest')

    if sys.platform.startswith('darwin'):
        port = unused_port()
    else:
        port = None

    container = docker.containers.run(
        image=image,
        detach=True,
        name='memcached-test-server-{}-{}'.format('latest', session_id),
        ports={
            '11211/tcp': port,
        },
        environment={
            'http.host': '0.0.0.0',
            'transport.host': '127.0.0.1',
        },
    )

    if sys.platform.startswith('darwin'):
        host = '0.0.0.0'
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection['NetworkSettings']['IPAddress']
        port = 11211

    delay = 0.1
    for i in range(20):
        try:
            conn = aiomcache.Client(host, port, loop=loop)
            loop.run_until_complete(conn.set(b'foo', b'bar'))
            break
        except ConnectionRefusedError:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start memcached server")

    yield {'host': host,
           'port': port,
           'container': container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def memcached_params(memcached_server: _TContainerInfo) -> _TMemcachedParams:
    return dict(host=memcached_server['host'],
                port=memcached_server['port'])


@pytest.fixture
def memcached(
    loop: asyncio.AbstractEventLoop,
    memcached_params: _TMemcachedParams
) -> Generator[aiomcache.Client, None, None]:
    conn = aiomcache.Client(loop=loop, **memcached_params)
    yield conn
    conn.close()
