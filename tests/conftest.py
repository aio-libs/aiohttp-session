import socket
import sys
import time
import uuid
from typing import Iterator

import aiomcache
import aioredis
import pytest
from docker import DockerClient, from_env as docker_from_env, models as docker_models

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict


class _ContainerInfo(TypedDict):
    host: str
    port: int
    container: docker_models.containers.Container


class _MemcachedParams(TypedDict):
    host: str
    port: int


def unused_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port: int = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope='session')
def session_id() -> str:
    """Unique session identifier, random string."""
    return str(uuid.uuid4())


@pytest.fixture(scope='session')
def docker() -> DockerClient:  # type: ignore[misc]  # No docker types.
    client = docker_from_env(version='auto')
    return client


@pytest.fixture(scope='session')
async def redis_server(  # type: ignore[misc]  # No docker types.
    docker: DockerClient,
    session_id: str,
) -> Iterator[_ContainerInfo]:
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
            'http.host': '0.0.0.0',  # noqa: S104
            'transport.host': '127.0.0.1',
        },
    )

    if sys.platform.startswith('darwin'):
        host = '0.0.0.0'  # noqa: S104
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection['NetworkSettings']['IPAddress']
        port = 6379

    delay = 0.1
    for _i in range(20):
        try:
            conn = await aioredis.from_url("redis://{}:{}".format(host, port))  # type: ignore[no-untyped-call]  # noqa: B950
            await conn.execute('SET', 'foo', 'bar')
            break
        except ConnectionRefusedError:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start redis server")

    yield {"host": host, "port": port, "container": container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def redis_url(redis_server: _ContainerInfo) -> str:  # type: ignore[misc]
    return "redis://{}:{}".format(redis_server["host"], redis_server["port"])


@pytest.fixture
async def redis(redis_url: str) -> Iterator[aioredis.Redis]:
    async def start(pool: aioredis.ConnectionPool) -> aioredis.Redis:
        return aioredis.Redis(connection_pool=pool)

    pool = aioredis.ConnectionPool.from_url(redis_url)
    redis = await start(pool)
    yield redis
    if redis is not None:
        redis.close()  # type: ignore[no-untyped-call]
        await pool.disconnect()


@pytest.fixture(scope='session')
async def memcached_server(  # type: ignore[misc]  # No docker types.
    docker: DockerClient,
    session_id: str,
) -> Iterator[_ContainerInfo]:

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
            'http.host': '0.0.0.0',  # noqa: S104
            'transport.host': '127.0.0.1',
        },
    )

    if sys.platform.startswith('darwin'):
        host = '0.0.0.0'  # noqa: S104
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection['NetworkSettings']['IPAddress']
        port = 11211

    delay = 0.1
    for _i in range(20):
        try:
            conn = aiomcache.Client(host, port)
            await conn.set(b'foo', b'bar')
            break
        except ConnectionRefusedError:
            time.sleep(delay)
            delay *= 2
    else:
        pytest.fail("Cannot start memcached server")

    yield {"host": host, "port": port, "container": container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def memcached_params(memcached_server: _ContainerInfo) -> _MemcachedParams:  # type: ignore[misc]
    return dict(host=memcached_server["host"], port=memcached_server["port"])


@pytest.fixture
def memcached(  # type: ignore[misc]
    memcached_params: _MemcachedParams
) -> Iterator[aiomcache.Client]:
    conn = aiomcache.Client(**memcached_params)
    yield conn
    conn.close()
