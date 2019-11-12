from aiohttp import web
from aiohttp.test_utils import TestClient

from typing import Awaitable, Callable

_TAiohttpClient = Callable[[web.Application], Awaitable[TestClient]]
