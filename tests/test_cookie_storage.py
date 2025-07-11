import json
import time
from http.cookies import SimpleCookie
from typing import Any, Dict, MutableMapping, cast

from aiohttp import web
from aiohttp.test_utils import TestClient
from aiohttp.typedefs import Handler

from aiohttp_session import (
    Session,
    SimpleCookieStorage,
    get_session,
    session_middleware,
)

from .typedefs import AiohttpClient


def make_cookie(
    client: TestClient[web.Request, web.Application], data: Dict[str, Any]
) -> None:
    session_data = {"session": data, "created": int(time.time())}

    value = json.dumps(session_data)
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": value})


def create_app(handler: Handler) -> web.Application:
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    app.router.add_route("GET", "/", handler)
    return app


async def test_create_new_session(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert cast(MutableMapping[str, Any], {}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    resp = await client.get("/")
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert session.created is not None
        assert cast(MutableMapping[str, Any], {"a": 1, "b": 2}) == session
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200


async def test_change_session(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    morsel = resp.cookies["AIOHTTP_SESSION"]
    cookie_data = json.loads(morsel.value)
    assert "session" in cookie_data
    assert "a" in cookie_data["session"]
    assert "b" in cookie_data["session"]
    assert "c" in cookie_data["session"]
    assert "created" in cookie_data
    assert cookie_data["session"]["a"] == 1
    assert cookie_data["session"]["b"] == 2
    assert cookie_data["session"]["c"] == 3
    assert morsel["httponly"]
    assert "/" == morsel["path"]


async def test_clear_cookie_on_session_invalidation(
    aiohttp_client: AiohttpClient,
) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200

    # Check the actual Set-Cookie header instead of resp.cookies
    # which used to leak the cookie jar details back into the resp.cookies
    set_cookie_header = resp.headers.get("Set-Cookie")
    assert set_cookie_header is not None

    # Parse the header
    cookie = SimpleCookie()
    cookie.load(set_cookie_header)
    assert "AIOHTTP_SESSION" in cookie

    # Verify the cookie was cleared (empty value)
    morsel = cookie["AIOHTTP_SESSION"]
    assert morsel.value == "{}"
    assert morsel["path"] == "/"
    assert morsel["httponly"] is True


async def test_dont_save_not_requested_session(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2})
    resp = await client.get("/")
    assert resp.status == 200
    assert "AIOHTTP_SESSION" not in resp.cookies
