from typing import Awaitable, Callable

from aiohttp import web
from aiohttp.test_utils import TestClient

AiohttpClient = Callable[[web.Application], Awaitable[TestClient]]
