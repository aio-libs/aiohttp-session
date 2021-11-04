import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from aiohttp_session import (
    SESSION_KEY,
    STORAGE_KEY,
    AbstractStorage,
    Session,
    get_session,
    new_session,
)


async def test_get_stored_session() -> None:
    req = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)
    req[SESSION_KEY] = session

    ret = await get_session(req)
    assert session is ret


async def test_session_is_not_stored() -> None:
    req = make_mocked_request("GET", "/")

    with pytest.raises(RuntimeError):
        await get_session(req)


async def test_storage_returns_not_session_on_load_session() -> None:
    req = make_mocked_request("GET", "/")

    class Storage:
        async def load_session(self, request: web.Request) -> None:
            return None

    req[STORAGE_KEY] = Storage()

    with pytest.raises(RuntimeError):
        await get_session(req)


async def test_get_new_session() -> None:
    req = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)

    class Storage(AbstractStorage):
        async def load_session(  # type: ignore[no-untyped-def]
            self,
            request: web.Request,
        ):
            pass

        async def save_session(
            self, request: web.Request, response: web.StreamResponse, session: Session
        ) -> None:
            pass

    req[SESSION_KEY] = session
    req[STORAGE_KEY] = Storage()

    ret = await new_session(req)
    assert ret is not session


async def test_get_new_session_no_storage() -> None:
    req = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)
    req[SESSION_KEY] = session

    with pytest.raises(RuntimeError):
        await new_session(req)


async def test_get_new_session_bad_return() -> None:
    req = make_mocked_request("GET", "/")

    class Storage(AbstractStorage):
        async def new_session(self):  # type: ignore[no-untyped-def]
            return ""

        async def load_session(self, request: web.Request) -> Session:
            return Session(None, data=None, new=True)

        async def save_session(
            self, request: web.Request, response: web.StreamResponse, session: Session
        ) -> None:
            pass

    req[STORAGE_KEY] = Storage()

    with pytest.raises(RuntimeError):
        await new_session(req)
