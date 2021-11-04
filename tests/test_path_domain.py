import json
import time
from http import cookies
from typing import Any, Optional

from aiohttp import web
from aiohttp.test_utils import TestClient

from aiohttp_session import (
    Handler,
    SimpleCookieStorage,
    get_session,
    session_middleware,
)

from .typedefs import AiohttpClient


def make_cookie(
    client: TestClient,
    data: Any,
    path: Optional[str] = None,
    domain: Optional[str] = None,
) -> None:
    session_data = {"session": data, "created": int(time.time())}
    C: cookies.SimpleCookie[str] = cookies.SimpleCookie()
    value = json.dumps(session_data)
    C["AIOHTTP_SESSION"] = value
    C["AIOHTTP_SESSION"]["path"] = path
    C["AIOHTTP_SESSION"]["domain"] = domain
    client.session.cookie_jar.update_cookies(C)


def create_app(
    handler: Handler, path: Optional[str] = None, domain: Optional[str] = None
) -> web.Application:
    storage = SimpleCookieStorage(max_age=10, path="/anotherpath", domain="127.0.0.1")
    middleware = session_middleware(storage)
    app = web.Application(middlewares=[middleware])
    app.router.add_route("GET", "/", handler)
    app.router.add_route("GET", "/anotherpath", handler)
    return app


async def test_with_same_path_domain(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2}, path="/anotherpath", domain="127.0.0.1")
    resp = await client.get("/anotherpath")
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
    assert "/anotherpath" == morsel["path"]
    assert "127.0.0.1" == morsel["domain"]


async def test_with_different_path(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2}, path="/NotTheSame", domain="127.0.0.1")
    resp = await client.get("/anotherpath")
    assert resp.status == 200
    morsel = resp.cookies["AIOHTTP_SESSION"]
    cookie_data = json.loads(morsel.value)
    assert "session" in cookie_data
    assert "a" not in cookie_data["session"]
    assert "b" not in cookie_data["session"]
    assert "c" in cookie_data["session"]
    assert "created" in cookie_data
    assert cookie_data["session"]["c"] == 3
    assert morsel["httponly"]
    assert "/anotherpath" == morsel["path"]
    assert "127.0.0.1" == morsel["domain"]


async def test_with_different_domain(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2}, path="/anotherpath", domain="localhost")
    resp = await client.get("/anotherpath")
    assert resp.status == 200
    morsel = resp.cookies["AIOHTTP_SESSION"]
    cookie_data = json.loads(morsel.value)
    assert "session" in cookie_data
    assert "a" not in cookie_data["session"]
    assert "b" not in cookie_data["session"]
    assert "c" in cookie_data["session"]
    assert "created" in cookie_data
    assert cookie_data["session"]["c"] == 3
    assert morsel["httponly"]
    assert "/anotherpath" == morsel["path"]
    assert "127.0.0.1" == morsel["domain"]


async def test_invalidate_with_same_path_domain(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session.invalidate()

        return web.Response(body=b"OK")

    client = await aiohttp_client(create_app(handler))
    make_cookie(client, {"a": 1, "b": 2}, path="/anotherpath", domain="127.0.0.1")
    resp = await client.get("/anotherpath")
    assert resp.status == 200
    morsel = resp.cookies["AIOHTTP_SESSION"]
    cookie_data = json.loads(morsel.value)
    assert {} == cookie_data
    assert morsel["httponly"]
    assert "/anotherpath" == morsel["path"]
    assert "127.0.0.1" == morsel["domain"]
