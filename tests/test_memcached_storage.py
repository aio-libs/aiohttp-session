import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, MutableMapping, Optional, cast

import aiomcache
from aiohttp import web
from aiohttp.test_utils import TestClient

from aiohttp_session import Handler, Session, get_session, session_middleware
from aiohttp_session.memcached_storage import MemcachedStorage

from .typedefs import AiohttpClient


def create_app(
    handler: Handler,
    memcached: aiomcache.Client,
    max_age: Optional[int] = None,
    key_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> web.Application:
    middleware = session_middleware(
        MemcachedStorage(memcached, max_age=max_age, key_factory=key_factory)
    )
    app = web.Application(middlewares=[middleware])
    app.router.add_route("GET", "/", handler)
    return app


async def make_cookie(
    client: TestClient, memcached: aiomcache.Client, data: Dict[str, Any]
) -> None:
    session_data = {"session": data, "created": int(time.time())}
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    storage_key = ("AIOHTTP_SESSION_" + key).encode("utf-8")
    await memcached.set(storage_key, bytes(value, "utf-8"))
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": key})


async def make_cookie_with_bad_value(
    client: TestClient, memcached: aiomcache.Client
) -> None:
    key = uuid.uuid4().hex
    storage_key = ("AIOHTTP_SESSION_" + key).encode("utf-8")
    await memcached.set(storage_key, b"")
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": key})


async def load_cookie(
    client: TestClient, memcached: aiomcache.Client
) -> Dict[str, Any]:
    cookies = client.session.cookie_jar.filter_cookies(client.make_url("/"))
    key = cookies["AIOHTTP_SESSION"]
    storage_key = ("AIOHTTP_SESSION_" + key.value).encode("utf-8")
    encoded = await memcached.get(storage_key)  # type: ignore[call-overload]
    s = encoded.decode("utf-8")
    return cast(Dict[str, Any], json.loads(s))


async def test_create_new_session(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    resp = await client.get("/")
    assert resp.status == 200


async def test_load_existing_session(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {"a": 1, "b": 12}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    await make_cookie(client, memcached, {"a": 1, "b": 12})
    resp = await client.get("/")
    assert resp.status == 200


async def test_load_bad_session(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    await make_cookie_with_bad_value(client, memcached)
    resp = await client.get("/")
    assert resp.status == 200


async def test_change_session(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    await make_cookie(client, memcached, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, memcached)
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
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    await make_cookie(client, memcached, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, memcached)
    assert {} == value
    morsel = resp.cookies["AIOHTTP_SESSION"]
    assert morsel["path"] == "/"
    assert morsel["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel["max-age"] == "0"


async def test_create_cookie_in_handler(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["a"] = 1
        session["b"] = 2
        return web.Response(body=b"OK", headers={"HOST": "example.com"})

    client = await aiohttp_client(create_app(handler, memcached))
    resp = await client.get("/")
    assert resp.status == 200

    value = await load_cookie(client, memcached)
    assert "session" in value
    assert "a" in value["session"]
    assert "b" in value["session"]
    assert "created" in value
    assert value["session"]["a"] == 1
    assert value["session"]["b"] == 2
    morsel = resp.cookies["AIOHTTP_SESSION"]
    assert morsel["httponly"]
    assert morsel["path"] == "/"
    storage_key = ("AIOHTTP_SESSION_" + morsel.value).encode("utf-8")
    exists = await memcached.get(storage_key)  # type: ignore[call-overload]
    assert exists


async def test_create_new_session_if_key_doesnt_exists_in_memcached(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert session.new
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler, memcached))
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": "invalid_key"})
    resp = await client.get("/")
    assert resp.status == 200


async def test_create_storage_with_custom_key_factory(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["key"] = "value"
        assert session.new
        return web.Response(body=b"OK")

    def key_factory() -> str:
        return "test-key"

    client = await aiohttp_client(create_app(handler, memcached, 8, key_factory))
    resp = await client.get("/")
    assert resp.status == 200

    assert resp.cookies["AIOHTTP_SESSION"].value == "test-key"

    value = await load_cookie(client, memcached)
    assert "key" in value["session"]
    assert value["session"]["key"] == "value"


async def test_memcached_session_fixation(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def login(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["k"] = "v"
        return web.Response()

    async def logout(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()
        return web.Response()

    app = create_app(login, memcached)
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


async def test_load_session_dont_load_expired_session(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
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

    client = await aiohttp_client(create_app(handler, memcached, 2))
    resp = await client.get("/")
    assert resp.status == 200

    await asyncio.sleep(5)

    resp = await client.get("/?exp=yes")
    assert resp.status == 200


async def test_memcached_max_age_over_30_days(
    aiohttp_client: AiohttpClient, memcached: aiomcache.Client
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["stored"] = "TEST_VALUE"
        session.max_age = 30 * 24 * 60 * 60 + 1
        assert session.new
        return web.Response(body=b"OK")

    async def get_value(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert not session.new
        response = session["stored"]
        return web.Response(body=response.encode("utf-8"))

    app = create_app(handler, memcached)
    app.router.add_route("GET", "/get_value", get_value)
    client = await aiohttp_client(app)

    resp = await client.get("/")
    assert resp.status == 200
    assert "AIOHTTP_SESSION" in resp.cookies
    storage_key = ("AIOHTTP_SESSION_" + resp.cookies["AIOHTTP_SESSION"].value).encode(
        "utf-8"
    )
    storage_value = await memcached.get(storage_key)  # type: ignore[call-overload]
    storage_value = json.loads(storage_value.decode("utf-8"))
    assert storage_value["session"]["stored"] == "TEST_VALUE"

    resp = await client.get("/get_value")
    assert resp.status == 200

    resp_content = await resp.text()
    assert resp_content == "TEST_VALUE"
