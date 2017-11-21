import pytest

from aiohttp_session import session_middleware


async def test_session_middleware_bad_storage():
    with pytest.raises(RuntimeError):
        session_middleware(None)
