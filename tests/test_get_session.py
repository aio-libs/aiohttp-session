import pytest

from aiohttp.test_utils import make_mocked_request

from aiohttp_session import (Session, get_session, SESSION_KEY, STORAGE_KEY,
                             new_session, AbstractStorage)


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


async def test_get_new_session():
    req = make_mocked_request('GET', '/')
    session = Session('identity', data=None, new=False)

    class Storage(AbstractStorage):
        async def load_session(self, request):
            pass

        async def save_session(self, request, response, session):
            pass

    req[SESSION_KEY] = session
    req[STORAGE_KEY] = Storage()

    ret = await new_session(req)
    assert ret is not session


async def test_get_new_session_no_storage():
    req = make_mocked_request('GET', '/')
    session = Session('identity', data=None, new=False)
    req[SESSION_KEY] = session

    with pytest.raises(RuntimeError):
        await new_session(req)


async def test_get_new_session_bad_return():
    req = make_mocked_request('GET', '/')

    class Storage(AbstractStorage):
        async def new_session(self):
            return ''

        async def load_session(self, request):
            pass

        async def save_session(self, request, response, session):
            pass

    req[STORAGE_KEY] = Storage()

    with pytest.raises(RuntimeError):
        await new_session(req)
