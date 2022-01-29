import time
from typing import Any, MutableMapping, cast

import pytest

from aiohttp_session import Session, SessionData


def test_create() -> None:
    s = Session("test_identity", data=None, new=True)
    assert s == cast(MutableMapping[str, Any], {})
    assert s.new
    assert "test_identity" == s.identity
    assert not s._changed
    assert s.created is not None


def test_create2() -> None:
    s = Session("test_identity", data={"session": {"some": "data"}}, new=False)
    assert s == cast(MutableMapping[str, Any], {"some": "data"})
    assert not s.new
    assert "test_identity" == s.identity
    assert not s._changed
    assert s.created is not None


def test_create3() -> None:
    s = Session(identity=1, data=None, new=True)
    assert s == cast(MutableMapping[str, Any], {})
    assert s.new
    assert s.identity == 1
    assert not s._changed
    assert s.created is not None


def test_set_new_identity_ok() -> None:
    s = Session(identity=1, data=None, new=True)
    assert s.new
    assert s.identity == 1

    s.set_new_identity(2)
    assert s.new
    assert s.identity == 2


def test_set_new_identity_for_not_new_session() -> None:
    s = Session(identity=1, data=None, new=False)
    with pytest.raises(RuntimeError):
        s.set_new_identity(2)


def test__repr__() -> None:
    s = Session("test_identity", data=None, new=True)
    assert str(s) == "<Session [new:True, changed:False, created:{0}] {{}}>".format(
        s.created
    )
    s["foo"] = "bar"
    assert str(
        s
    ) == "<Session [new:True, changed:True, created:{0}]" " {{'foo': 'bar'}}>".format(
        s.created
    )


def test__repr__2() -> None:
    created = int(time.time()) - 1000
    session_data: SessionData = {"session": {"key": 123}, "created": created}
    s = Session("test_identity", data=session_data, new=False)
    assert str(
        s
    ) == "<Session [new:False, changed:False, created:{0}]" " {{'key': 123}}>".format(
        created
    )
    s.invalidate()
    assert str(s) == "<Session [new:False, changed:True, created:{0}] {{}}>".format(
        created
    )


def test_invalidate() -> None:
    s = Session("test_identity", data={"session": {"foo": "bar"}}, new=False)
    assert s == cast(MutableMapping[str, Any], {"foo": "bar"})
    assert not s._changed

    s.invalidate()
    assert s == cast(MutableMapping[str, Any], {})
    assert s._changed
    # Mypy bug: https://github.com/python/mypy/issues/11853
    assert s.created is not None  # type: ignore[unreachable]


def test_invalidate2() -> None:
    s = Session("test_identity", data={"session": {"foo": "bar"}}, new=False)
    assert s == cast(MutableMapping[str, Any], {"foo": "bar"})
    assert not s._changed

    s.invalidate()
    assert s == cast(MutableMapping[str, Any], {})
    assert s._changed
    # Mypy bug: https://github.com/python/mypy/issues/11853
    assert s.created is not None  # type: ignore[unreachable]


def test_operations() -> None:
    s = Session("test_identity", data=None, new=False)
    assert s == cast(MutableMapping[str, Any], {})
    assert len(s) == 0
    assert list(s) == []
    assert "foo" not in s
    assert "key" not in s

    s = Session("test_identity", data={"session": {"foo": "bar"}}, new=False)
    assert len(s) == 1
    assert s == cast(MutableMapping[str, Any], {"foo": "bar"})
    assert list(s) == ["foo"]
    assert "foo" in s
    assert "key" not in s

    s["key"] = "value"
    assert len(s) == 2
    assert s == cast(MutableMapping[str, Any], {"foo": "bar", "key": "value"})
    assert sorted(s) == ["foo", "key"]
    assert "foo" in s
    assert "key" in s

    del s["key"]
    assert len(s) == 1
    assert s == cast(MutableMapping[str, Any], {"foo": "bar"})
    assert list(s) == ["foo"]
    assert "foo" in s
    assert "key" not in s

    s.pop("foo")
    assert len(s) == 0
    assert s == cast(MutableMapping[str, Any], {})
    assert list(s) == []
    assert "foo" not in s
    assert "key" not in s


def test_change() -> None:
    created = int(time.time())
    s = Session(
        "test_identity",
        new=False,
        data={"session": {"a": {"key": "value"}}, "created": created},
    )
    assert not s._changed

    s["a"]["key2"] = "val2"
    assert not s._changed
    assert cast(MutableMapping[str, Any], {"a": {"key": "value", "key2": "val2"}}) == s

    assert s.created == created

    s.changed()
    assert s._changed
    # Mypy bug: https://github.com/python/mypy/issues/11853
    assert s.created == created  # type: ignore[unreachable]
    assert cast(MutableMapping[str, Any], {"a": {"key": "value", "key2": "val2"}}) == s
