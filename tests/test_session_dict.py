import unittest
import time

from aiohttp_session import Session


class SessionTests(unittest.TestCase):

    def test_create(self):
        s = Session('test_identity', new=True)
        self.assertEqual(s, {})
        self.assertTrue(s.new)
        self.assertEqual('test_identity', s.identity)
        self.assertFalse(s._changed)
        self.assertIsNotNone(s.created)

    def test_create2(self):
        s = Session('test_identity', data={'session': {'some': 'data'}})
        self.assertEqual(s, {'some': 'data'})
        self.assertFalse(s.new)
        self.assertEqual('test_identity', s.identity)
        self.assertFalse(s._changed)
        self.assertIsNotNone(s.created)

    def test_create3(self):
        s = Session(identity=1, new=True)
        self.assertEqual(s, {})
        self.assertTrue(s.new)
        self.assertEqual(s.identity, 1)
        self.assertFalse(s._changed)
        self.assertIsNotNone(s.created)

    def test__repr__(self):
        s = Session('test_identity', new=True)
        self.assertEqual(
            str(s),
            '<Session [new:True, changed:False, created:{0}] {{}}>'.format(
                s.created))
        s['foo'] = 'bar'
        self.assertEqual(
            str(s),
            "<Session [new:True, changed:True, created:{0}]"
            " {{'foo': 'bar'}}>".format(s.created))

    def test__repr__2(self):
        created = int(time.time()) - 1000
        session_data = {
            'session': {
                'key': 123
            },
            'created': created
        }
        s = Session('test_identity', data=session_data, new=False)
        self.assertEqual(
            str(s),
            "<Session [new:False, changed:False, created:{0}]"
            " {{'key': 123}}>".format(created))
        s.invalidate()
        self.assertEqual(
            str(s),
            "<Session [new:False, changed:True, created:{0}] {{}}>".format(
                created))

    def test_invalidate(self):
        s = Session('test_identity', data={'session': {'foo': 'bar'}})
        self.assertEqual(s, {'foo': 'bar'})
        self.assertFalse(s._changed)

        s.invalidate()
        self.assertEqual(s, {})
        self.assertTrue(s._changed)
        self.assertIsNotNone(s.created)

    def test_invalidate2(self):
        s = Session('test_identity', data={'session': {'foo': 'bar'}})
        self.assertEqual(s, {'foo': 'bar'})
        self.assertFalse(s._changed)

        s.invalidate()
        self.assertEqual(s, {})
        self.assertTrue(s._changed)
        self.assertIsNotNone(s.created)

    def test_operations(self):
        s = Session('test_identity')
        self.assertEqual(s, {})
        self.assertEqual(len(s), 0)
        self.assertEqual(list(s), [])
        self.assertNotIn('foo', s)
        self.assertNotIn('key', s)

        s = Session('test_identity', data={'session': {'foo': 'bar'}})
        self.assertEqual(len(s), 1)
        self.assertEqual(s, {'foo': 'bar'})
        self.assertEqual(list(s), ['foo'])
        self.assertIn('foo', s)
        self.assertNotIn('key', s)

        s['key'] = 'value'
        self.assertEqual(len(s), 2)
        self.assertEqual(s, {'foo': 'bar', 'key': 'value'})
        self.assertEqual(sorted(s), ['foo', 'key'])
        self.assertIn('foo', s)
        self.assertIn('key', s)

        del s['key']
        self.assertEqual(len(s), 1)
        self.assertEqual(s, {'foo': 'bar'})
        self.assertEqual(list(s), ['foo'])
        self.assertIn('foo', s)
        self.assertNotIn('key', s)

        s.pop('foo')
        self.assertEqual(len(s), 0)
        self.assertEqual(s, {})
        self.assertEqual(list(s), [])
        self.assertNotIn('foo', s)
        self.assertNotIn('key', s)

    def test_change(self):
        created = int(time.time())
        s = Session('test_identity', new=False, data={
            'session': {
                'a': {'key': 'value'}
            },
            'created': created
        })
        self.assertFalse(s._changed)

        s['a']['key2'] = 'val2'
        self.assertFalse(s._changed)
        self.assertEqual({'a': {'key': 'value',
                                'key2': 'val2'}},
                         s)
        self.assertEqual(s.created, created)

        s.changed()
        self.assertTrue(s._changed)
        self.assertEqual({'a': {'key': 'value',
                                'key2': 'val2'}},
                         s)
        self.assertEqual(s.created, created)
