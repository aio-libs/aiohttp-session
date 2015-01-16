import unittest
from unittest import mock

from aiohttp.web import Request, HttpVersion
from aiohttp import CIMultiDict, RawRequestMessage

from aiohttp_session import Session, get_session, SESSION_KEY


class TestGetSession(unittest.TestCase):

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
        req = self.make_request('GET', '/')
        session = Session()
        req[SESSION_KEY] = session

        self.assertIs(session, get_session(req))

    def test_session_is_not_stored(self):
        req = self.make_request('GET', '/')

        with self.assertRaises(RuntimeError):
            get_session(req)
