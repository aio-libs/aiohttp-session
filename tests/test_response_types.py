import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.typedefs import Handler

from aiohttp_session import (
    SESSION_KEY,
    SimpleCookieStorage,
    get_session,
    session_middleware,
)

from .typedefs import AiohttpClient


def create_app(*handlers: tuple[str, Handler]) -> web.Application:
    middleware = session_middleware(SimpleCookieStorage())
    app = web.Application(middlewares=[middleware])
    for url, handler in handlers:
        app.router.add_route("GET", url, handler)
    return app


async def test_stream_response(aiohttp_client: AiohttpClient) -> None:
    async def stream_response(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        session["will_not"] = "show up"
        return web.StreamResponse()

    client = await aiohttp_client(create_app(("/stream", stream_response)))

    resp = await client.get("/stream")
    assert resp.status == 200
    assert SESSION_KEY.upper() not in resp.cookies


async def test_bad_response_type(aiohttp_client: AiohttpClient) -> None:
    async def bad_response(request: web.Request):  # type: ignore[no-untyped-def]
        return ""

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request("GET", "/")
    with pytest.raises(RuntimeError):
        await middleware(req, bad_response)


async def test_prepared_response_type(aiohttp_client: AiohttpClient) -> None:
    async def prepared_response(request: web.Request) -> web.StreamResponse:
        resp = web.Response()
        await resp.prepare(request)
        return resp

    middleware = session_middleware(SimpleCookieStorage())
    req = make_mocked_request("GET", "/")
    with pytest.raises(RuntimeError):
        await middleware(req, prepared_response)


async def test_file_response_saves_session(
    aiohttp_client: AiohttpClient, tmp_path: Path
) -> None:
    path = tmp_path / "download.txt"
    path.write_text("download content")

    async def download(request: web.Request) -> web.FileResponse:
        session = await get_session(request)
        session["downloads"] = session.get("downloads", 0) + 1
        return web.FileResponse(path)

    client = await aiohttp_client(create_app(("/file", download)))
    for count in (1, 2):
        resp = await client.get("/file")
        assert resp.status == 200
        assert await resp.text() == "download content"
        cookie = resp.cookies["AIOHTTP_SESSION"]
        assert json.loads(cookie.value)["session"] == {"downloads": count}


async def test_file_response_without_session(
    aiohttp_client: AiohttpClient, tmp_path: Path
) -> None:
    path = tmp_path / "download.txt"
    path.write_text("download content")

    async def download(request: web.Request) -> web.FileResponse:
        return web.FileResponse(path)

    client = await aiohttp_client(create_app(("/file", download)))
    resp = await client.get("/file")
    assert resp.status == 200
    assert await resp.text() == "download content"
    assert "AIOHTTP_SESSION" not in resp.cookies
