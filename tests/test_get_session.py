import asyncio
import unittest
from unittest import mock

from aiohttp.web import Request, HttpVersion
from aiohttp import CIMultiDict, RawRequestMessage

from aiohttp_session import Session, get_session, SESSION_KEY


class TestGetSession(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.stop()
        self.loop.run_forever()
        self.loop.close()

    def make_request(self, method, path, headers=CIMultiDict(), *,
                     version=HttpVersion(1, 1), closing=False):
        self.app = mock.Mock()
        message = RawRequestMessage(method, path, version, headers, closing,
                                    False)
        self.payload = mock.Mock()
        self.transport = mock.Mock()
        self.writer = mock.Mock()
        self.reader = mock.Mock()
        req = Request(self.app, message, self.payload,
                      self.transport, self.reader, self.writer)
        return req

    def test_get_stored_session(self):

        @asyncio.coroutine
        def go():
            req = self.make_request('GET', '/')
            session = Session('identity')
            req[SESSION_KEY] = session

            ret = yield from get_session(req)
            self.assertIs(session, ret)

        self.loop.run_until_complete(go())

    def test_session_is_not_stored(self):

        @asyncio.coroutine
        def go():
            req = self.make_request('GET', '/')

            with self.assertRaises(RuntimeError):
                yield from get_session(req)

        self.loop.run_until_complete(go())
