import asyncio
import pytest

from aiohttp.test_utils import make_mocked_request

from aiohttp_session import Session, get_session, SESSION_KEY


@asyncio.coroutine
def test_get_stored_session():
    req = make_mocked_request('GET', '/')
    session = Session('identity', data=None, new=False)
    req[SESSION_KEY] = session

    ret = yield from get_session(req)
    assert session is ret


@asyncio.coroutine
def test_session_is_not_stored():
    req = make_mocked_request('GET', '/')

    with pytest.raises(RuntimeError):
        yield from get_session(req)
