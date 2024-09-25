from __future__ import annotations

import asyncio
import gc
import socket
import sys
import time
import uuid
from typing import AsyncIterator, Iterator, TypedDict

import aiomcache
import pytest
from docker import DockerClient, from_env as docker_from_env, models as docker_models
from redis import asyncio as aioredis


class _ContainerInfo(TypedDict):
    host: str
    port: int
    container: docker_models.containers.Container


class _MemcachedParams(TypedDict):
    host: str
    port: int


def unused_port() -> int:  # pragma: no cover
    """Only used for people testing on OS X."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port: int = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def session_id() -> str:
    """Unique session identifier, random string."""
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def docker() -> DockerClient:  # type: ignore[misc]  # No docker types.
    client = docker_from_env(version="auto")
    yield client
    client.close()


@pytest.fixture(scope="session")
async def redis_server(  # type: ignore[misc]  # No docker types.
    docker: DockerClient,
    session_id: str,
) -> Iterator[_ContainerInfo]:
    image = "redis:{}".format("latest")

    if sys.platform.startswith("darwin"):  # pragma: no cover
        port = unused_port()
    else:
        port = None

    container = docker.containers.run(
        image=image,
        detach=True,
        name="redis-test-server-{}-{}".format("latest", session_id),
        ports={
            "6379/tcp": port,
        },
        environment={
            "http.host": "0.0.0.0",
            "transport.host": "127.0.0.1",
        },
    )

    if sys.platform.startswith("darwin"):  # pragma: no cover
        host = "0.0.0.0"
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection["NetworkSettings"]["IPAddress"]
        port = 6379

    delay = 0.1
    for _i in range(20):  # pragma: no cover
        try:
            conn = aioredis.from_url(f"redis://{host}:{port}")  # type: ignore[no-untyped-call]
            await conn.set("foo", "bar")
            break
        except aioredis.ConnectionError:
            time.sleep(delay)
            delay *= 2
        finally:
            await conn.aclose()
    else:  # pragma: no cover
        pytest.fail("Cannot start redis server")

    yield {"host": host, "port": port, "container": container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def redis_url(redis_server: _ContainerInfo) -> str:  # type: ignore[misc]
    return "redis://{}:{}".format(redis_server["host"], redis_server["port"])


@pytest.fixture
async def redis(
    redis_url: str,
) -> AsyncIterator[aioredis.Redis]:
    async def start(pool: aioredis.ConnectionPool) -> aioredis.Redis:
        return aioredis.Redis(connection_pool=pool)

    pool = aioredis.ConnectionPool.from_url(redis_url)
    redis = await start(pool)
    yield redis
    await redis.aclose()
    await pool.disconnect()


@pytest.fixture(scope="session")
async def memcached_server(  # type: ignore[misc]  # No docker types.
    docker: DockerClient,
    session_id: str,
) -> AsyncIterator[_ContainerInfo]:
    image = "memcached:{}".format("latest")

    if sys.platform.startswith("darwin"):  # pragma: no cover
        port = unused_port()
    else:
        port = None

    container = docker.containers.run(
        image=image,
        detach=True,
        name="memcached-test-server-{}-{}".format("latest", session_id),
        ports={
            "11211/tcp": port,
        },
        environment={
            "http.host": "0.0.0.0",
            "transport.host": "127.0.0.1",
        },
    )

    if sys.platform.startswith("darwin"):  # pragma: no cover
        host = "0.0.0.0"
    else:
        inspection = docker.api.inspect_container(container.id)
        host = inspection["NetworkSettings"]["IPAddress"]
        port = 11211

    delay = 0.1
    for _i in range(20):  # pragma: no cover
        try:
            conn = aiomcache.Client(host, port)
            await conn.set(b"foo", b"bar")
            break
        except ConnectionRefusedError:
            time.sleep(delay)
            delay *= 2
        finally:
            await conn.close()
    else:  # pragma: no cover
        pytest.fail("Cannot start memcached server")

    yield {"host": host, "port": port, "container": container}

    container.kill(signal=9)
    container.remove(force=True)


@pytest.fixture
def memcached_params(  # type: ignore[misc]
    memcached_server: _ContainerInfo,
) -> _MemcachedParams:
    return dict(host=memcached_server["host"], port=memcached_server["port"])


@pytest.fixture
async def memcached(memcached_params: _MemcachedParams) -> AsyncIterator[aiomcache.Client]:
    conn = aiomcache.Client(**memcached_params)
    yield conn
    await conn.close()
