from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, MutableMapping, Optional, cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from pytest_mock import MockFixture
from redis import asyncio as aioredis

from aiohttp_session import Handler, Session, get_session, session_middleware
from aiohttp_session.redis_storage import RedisStorage

from .typedefs import AiohttpClient


def create_app(
    handler: Handler,
    redis: aioredis.Redis[bytes],
    max_age: Optional[int] = None,
    key_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> web.Application:
    middleware = session_middleware(
        RedisStorage(redis, max_age=max_age, key_factory=key_factory)
    )
    app = web.Application(middlewares=[middleware])
    app.router.add_route("GET", "/", handler)
    return app


async def make_cookie(
    client: TestClient, redis: aioredis.Redis[bytes], data: Dict[Any, Any]
) -> None:
    session_data = {"session": data, "created": int(time.time())}
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    await redis.set("AIOHTTP_SESSION_" + key, value)
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": key})


async def make_cookie_with_bad_value(client: TestClient, redis: aioredis.Redis[bytes]) -> None:
    key = uuid.uuid4().hex
    await redis.set("AIOHTTP_SESSION_" + key, "")
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": key})


async def load_cookie(client: TestClient, redis: aioredis.Redis[bytes]) -> Any:
    cookies = client.session.cookie_jar.filter_cookies(client.make_url("/"))
    key = cookies["AIOHTTP_SESSION"]
    value_bytes = await redis.get("AIOHTTP_SESSION_" + key.value)
    return None if value_bytes is None else json.loads(value_bytes)


async def test_create_new_session(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get("/")
    assert resp.status == 200


async def test_load_existing_session(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {"a": 1, "b": 12}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {"a": 1, "b": 12})
    resp = await client.get("/")
    assert resp.status == 200


async def test_load_bad_session(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie_with_bad_value(client, redis)
    resp = await client.get("/")
    assert resp.status == 200


async def test_change_session(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, redis)
    assert "session" in value
    assert "a" in value["session"]
    assert "b" in value["session"]
    assert "c" in value["session"]
    assert "created" in value
    assert value["session"]["a"] == 1
    assert value["session"]["b"] == 2
    assert value["session"]["c"] == 3
    morsel = resp.cookies["AIOHTTP_SESSION"]
    assert morsel["httponly"]
    assert "/" == morsel["path"]


async def test_clear_cookie_on_session_invalidation(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    await make_cookie(client, redis, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, redis)
    assert {} == value
    morsel = resp.cookies["AIOHTTP_SESSION"]
    assert morsel["path"] == "/"
    assert morsel["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel["max-age"] == "0"


async def test_create_cookie_in_handler(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["a"] = 1
        session["b"] = 2
        return web.Response(body=b"OK", headers={"HOST": "example.com"})

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, redis)
    assert "session" in value
    assert "a" in value["session"]
    assert "b" in value["session"]
    assert "created" in value
    assert value["session"]["a"] == 1
    assert value["session"]["b"] == 2
    morsel = resp.cookies["AIOHTTP_SESSION"]
    assert morsel["httponly"]
    assert morsel["path"] == "/"
    exists = await redis.exists("AIOHTTP_SESSION_" + morsel.value)
    assert exists


async def test_set_ttl_on_session_saving(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["a"] = 1
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis, max_age=10))
    resp = await client.get("/")
    assert resp.status == 200

    key = resp.cookies["AIOHTTP_SESSION"].value

    ttl = await redis.ttl("AIOHTTP_SESSION_" + key)

    assert ttl > 9
    assert ttl <= 10


async def test_set_ttl_manually_set(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.max_age = 10
        session["a"] = 1
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    resp = await client.get("/")
    assert resp.status == 200

    key = resp.cookies["AIOHTTP_SESSION"].value

    ttl = await redis.ttl("AIOHTTP_SESSION_" + key)

    assert ttl > 9
    assert ttl <= 10


async def test_create_new_session_if_key_doesnt_exists_in_redis(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert session.new
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis))
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": "invalid_key"})
    resp = await client.get("/")
    assert resp.status == 200


async def test_create_storage_with_custom_key_factory(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["key"] = "value"
        assert session.new
        return web.Response(body=b"OK")

    def key_factory() -> str:
        return "test-key"

    client = await aiohttp_client(create_app(handler, redis, 8, key_factory))
    resp = await client.get("/")
    assert resp.status == 200

    assert resp.cookies["AIOHTTP_SESSION"].value == "test-key"

    value = await load_cookie(client, redis)
    assert "key" in value["session"]
    assert value["session"]["key"] == "value"


async def test_redis_session_fixation(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def login(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["k"] = "v"
        return web.Response()

    async def logout(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()
        return web.Response()

    app = create_app(login, redis)
    app.router.add_route("DELETE", "/", logout)
    client = await aiohttp_client(app)
    resp = await client.get("/")
    assert "AIOHTTP_SESSION" in resp.cookies
    evil_cookie = resp.cookies["AIOHTTP_SESSION"].value
    resp = await client.delete("/")
    assert resp.cookies["AIOHTTP_SESSION"].value == ""
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": evil_cookie})
    resp = await client.get("/")
    assert resp.cookies["AIOHTTP_SESSION"].value != evil_cookie


async def test_redis_from_create_pool(redis_url: str) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        pass

    redis = aioredis.from_url(redis_url)
    create_app(handler=handler, redis=redis)
    await redis.close()


async def test_not_redis_provided_to_storage() -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        pass

    with pytest.raises(TypeError):
        create_app(handler=handler, redis=None)  # type: ignore[arg-type]


async def test_no_aioredis_installed(mocker: MockFixture) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        pass

    mocker.patch("aiohttp_session.redis_storage.aioredis", None)
    with pytest.raises(RuntimeError):
        create_app(handler=handler, redis=None)  # type: ignore[arg-type]


async def test_old_aioredis_version(mocker: MockFixture) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        pass

    mocker.patch("aiohttp_session.redis_storage.REDIS_VERSION", (0, 3, "dev0"))
    with pytest.raises(RuntimeError):
        create_app(handler=handler, redis=None)  # type: ignore[arg-type]


async def test_load_session_dont_load_expired_session(
    aiohttp_client: AiohttpClient, redis: aioredis.Redis[bytes]
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        exp_param = request.rel_url.query.get("exp", None)
        if exp_param is None:
            session["a"] = 1
            session["b"] = 2
        else:
            assert cast(MutableMapping[str, Any], {}) == session

        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, redis, 2))
    resp = await client.get("/")
    assert resp.status == 200

    await asyncio.sleep(5)

    resp = await client.get("/?exp=yes")
    assert resp.status == 200
