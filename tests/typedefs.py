from aiohttp import web
from aiohttp.test_utils import TestClient

from typing import Awaitable, Callable

AiohttpClient = Callable[[web.Application], Awaitable[TestClient]]
