import pytest

from aiohttp.test_utils import make_mocked_request

from aiohttp_session import Session, get_session, SESSION_KEY, STORAGE_KEY


async def test_get_stored_session():
    req = make_mocked_request('GET', '/')
    session = Session('identity', data=None, new=False)
    req[SESSION_KEY] = session

    ret = await get_session(req)
    assert session is ret


async def test_session_is_not_stored():
    req = make_mocked_request('GET', '/')

    with pytest.raises(RuntimeError):
        await get_session(req)


async def test_storage_returns_not_session_on_load_session():
    req = make_mocked_request('GET', '/')

    class Storage():
        async def load_session(self, request):
            return None

    req[STORAGE_KEY] = Storage()

    with pytest.raises(RuntimeError):
        await get_session(req)
