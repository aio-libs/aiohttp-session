import json
import time
from functools import partial
from typing import Any, Dict, Optional
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient

from aiohttp_session import (
    Handler,
    SimpleCookieStorage,
    get_session,
    setup as setup_middleware,
)

from .typedefs import AiohttpClient


def make_cookie(client: TestClient, data: Dict[str, Any]) -> None:
    session_data = {"session": data, "created": int(time.time())}

    value = json.dumps(session_data)
    client.session.cookie_jar.update_cookies({"AIOHTTP_SESSION": value})


def create_app(handler: Handler) -> web.Application:
    app = web.Application()
    setup_middleware(app, SimpleCookieStorage(max_age=10))
    app.router.add_route("GET", "/", handler)
    return app


async def test_max_age_also_returns_expires(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request) -> web.Response:
        session = await get_session(request)
        session["c"] = 3
        return web.Response(body=b"OK")

    with mock.patch("time.time") as m_clock:
        m_clock.return_value = 0.0

        client = await aiohttp_client(create_app(handler))
        make_cookie(client, {"a": 1, "b": 2})
        async with client.get("/") as resp:
            assert resp.status == 200
            assert "expires=Thu, 01-Jan-1970 00:00:10 GMT" in resp.headers["SET-COOKIE"]


async def test_max_age_session_reset(aiohttp_client: AiohttpClient) -> None:
    async def handler(request: web.Request, n: Optional[str] = None) -> web.Response:
        session = await get_session(request)
        if n:
            session[n] = True
        return web.json_response(session._mapping)

    app = create_app(handler)
    app.router.add_route("GET", "/a", partial(handler, n="a"))
    app.router.add_route("GET", "/b", partial(handler, n="b"))
    app.router.add_route("GET", "/c", partial(handler, n="c"))
    client = await aiohttp_client(app)

    with mock.patch("time.time") as m_clock:
        m_clock.return_value = 0.0
        # Initialise the session (with a 10 second max_age).
        async with client.get("/a") as resp:
            c = resp.cookies["AIOHTTP_SESSION"]
            assert "00:00:10" in c["expires"]
            assert {"a"} == json.loads(c.value)["session"].keys()

        m_clock.return_value = 8.0
        # Here we update the session, which should reset expiry time to 18 seconds past.
        async with client.get("/b") as resp:
            c = resp.cookies["AIOHTTP_SESSION"]
            assert "00:00:18" in c["expires"]
            assert {"a", "b"} == json.loads(c.value)["session"].keys()

        m_clock.return_value = 15.0
        # Because the session has been updated, it should not have expired yet.
        async with client.get("/") as resp:
            sess = await resp.json()
            assert {"a", "b"} == sess.keys()

        async with client.get("/c") as resp:
            c = resp.cookies["AIOHTTP_SESSION"]
            assert "00:00:25" in c["expires"]
            assert {"a", "b", "c"} == json.loads(c.value)["session"].keys()

        m_clock.return_value = 30.0
        # Here the session should have expired.
        async with client.get("/") as resp:
            sess = await resp.json()
            assert sess == {}
