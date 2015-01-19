import unittest

from aiohttp_session import Session


class SessionTests(unittest.TestCase):

    def test_create(self):
        s = Session('test_identity', new=True)
        self.assertEqual(s, {})
        self.assertTrue(s.new)
        self.assertEqual('test_identity', s.identity)
        self.assertFalse(s._changed)

    def test_create2(self):
        s = Session('test_identity', data={'some': 'data'})
        self.assertEqual(s, {'some': 'data'})
        self.assertFalse(s.new)
        self.assertEqual('test_identity', s.identity)
        self.assertFalse(s._changed)

    def test_create3(self):
        s = Session(identity=1, new=True)
        self.assertEqual(s, {})
        self.assertTrue(s.new)
        self.assertEqual(s.identity, 1)
        self.assertFalse(s._changed)

    def test__repr__(self):
        s = Session('test_identity', new=True)
        self.assertEqual(str(s), '<Session [new:True, changed:False] {}>')
        s['foo'] = 'bar'
        self.assertEqual(str(s),
                         "<Session [new:True, changed:True] {'foo': 'bar'}>")

    def test__repr__2(self):
        s = Session('test_identity', data={'key': 123}, new=False)
        self.assertEqual(str(s),
                         "<Session [new:False, changed:False] {'key': 123}>")
        s.invalidate()
        self.assertEqual(str(s), "<Session [new:False, changed:True] {}>")

    def test_invalidate(self):
        s = Session('test_identity', data={'foo': 'bar'})
        self.assertEqual(s, {'foo': 'bar'})
        self.assertFalse(s._changed)

        s.invalidate()
        self.assertEqual(s, {})
        self.assertTrue(s._changed)

    def test_invalidate2(self):
        s = Session('test_identity', data={'foo': 'bar'})
        self.assertEqual(s, {'foo': 'bar'})
        self.assertFalse(s._changed)

        s.invalidate()
        self.assertEqual(s, {})
        self.assertTrue(s._changed)

    def test_operations(self):
        s = Session('test_identity')
        self.assertEqual(s, {})
        self.assertEqual(len(s), 0)
        self.assertEqual(list(s), [])
        self.assertNotIn('foo', s)
        self.assertNotIn('key', s)

        s = Session('test_identity', data={'foo': 'bar'})
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
        s = Session('test_identity', new=False, data={'a': {'key': 'value'}})
        self.assertFalse(s._changed)

        s['a']['key2'] = 'val2'
        self.assertFalse(s._changed)
        self.assertEqual({'a': {'key': 'value',
                                'key2': 'val2'}},
                         s)

        s.changed()
        self.assertTrue(s._changed)
        self.assertEqual({'a': {'key': 'value',
                                'key2': 'val2'}},
                         s)
