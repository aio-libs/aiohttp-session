import pytest

from aiohttp_session import session_middleware


async def test_session_middleware_bad_storage() -> None:
    with pytest.raises(RuntimeError):
        # Ignoring typing since parameter type is wrong on purpose
        session_middleware(None)  # type: ignore[arg-type]
