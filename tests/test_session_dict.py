import time

from aiohttp_session import Session


def test_create():
    s = Session('test_identity', data=None, new=True)
    assert s == {}
    assert s.new
    assert 'test_identity' == s.identity
    assert not s._changed
    assert s.created is not None


def test_create2():
    s = Session('test_identity', data={'session': {'some': 'data'}},
                new=False)
    assert s == {'some': 'data'}
    assert not s.new
    assert 'test_identity' == s.identity
    assert not s._changed
    assert s.created is not None


def test_create3():
    s = Session(identity=1, data=None, new=True)
    assert s == {}
    assert s.new
    assert s.identity == 1
    assert not s._changed
    assert s.created is not None


def test__repr__():
    s = Session('test_identity', data=None, new=True)
    assert str(s) == \
        '<Session [new:True, changed:False, created:{0}] {{}}>'.format(
            s.created)
    s['foo'] = 'bar'
    assert str(s) == \
        "<Session [new:True, changed:True, created:{0}]" \
        " {{'foo': 'bar'}}>".format(s.created)


def test__repr__2():
    created = int(time.time()) - 1000
    session_data = {
        'session': {
            'key': 123
        },
        'created': created
    }
    s = Session('test_identity', data=session_data, new=False)
    assert str(s) == \
        "<Session [new:False, changed:False, created:{0}]" \
        " {{'key': 123}}>".format(created)
    s.invalidate()
    assert str(s) == \
        "<Session [new:False, changed:True, created:{0}] {{}}>".format(
            created)


def test_invalidate():
    s = Session('test_identity', data={'session': {'foo': 'bar'}},
                new=False)
    assert s == {'foo': 'bar'}
    assert not s._changed

    s.invalidate()
    assert s == {}
    assert s._changed
    assert s.created is not None


def test_invalidate2():
    s = Session('test_identity', data={'session': {'foo': 'bar'}},
                new=False)
    assert s == {'foo': 'bar'}
    assert not s._changed

    s.invalidate()
    assert s == {}
    assert s._changed
    assert s.created is not None


def test_operations():
    s = Session('test_identity', data=None, new=False)
    assert s == {}
    assert len(s) == 0
    assert list(s) == []
    assert 'foo' not in s
    assert 'key' not in s

    s = Session('test_identity', data={'session': {'foo': 'bar'}},
                new=False)
    assert len(s) == 1
    assert s == {'foo': 'bar'}
    assert list(s) == ['foo']
    assert 'foo' in s
    assert 'key' not in s

    s['key'] = 'value'
    assert len(s) == 2
    assert s == {'foo': 'bar', 'key': 'value'}
    assert sorted(s) == ['foo', 'key']
    assert 'foo' in s
    assert 'key' in s

    del s['key']
    assert len(s) == 1
    assert s == {'foo': 'bar'}
    assert list(s) == ['foo']
    assert 'foo' in s
    assert 'key' not in s

    s.pop('foo')
    assert len(s) == 0
    assert s == {}
    assert list(s) == []
    assert 'foo' not in s
    assert 'key' not in s


def test_change():
    created = int(time.time())
    s = Session('test_identity', new=False, data={
        'session': {
            'a': {'key': 'value'}
        },
        'created': created
    })
    assert not s._changed

    s['a']['key2'] = 'val2'
    assert not s._changed
    assert {'a': {'key': 'value',
                  'key2': 'val2'}} == s

    assert s.created == created

    s.changed()
    assert s._changed
    assert {'a': {'key': 'value',
                  'key2': 'val2'}} == s
    assert s.created == created
