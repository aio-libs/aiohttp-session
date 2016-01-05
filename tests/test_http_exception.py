import asyncio
import socket
import unittest

from aiohttp import web, request
from aiohttp_session import (session_middleware,
                             get_session, SimpleCookieStorage)


class TestHttpException(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.srv = None
        self.handler = None

    def tearDown(self):
        self.loop.run_until_complete(self.handler.finish_connections())
        self.srv.close()
        self.loop.stop()
        self.loop.run_forever()
        self.loop.close()

    def find_unused_port(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    @asyncio.coroutine
    def create_server(self, routes):
        middleware = session_middleware(SimpleCookieStorage())
        app = web.Application(middlewares=[middleware], loop=self.loop)
        for method, path, handler in routes:
            app.router.add_route(method, path, handler)

        port = self.find_unused_port()
        handler = app.make_handler()
        srv = yield from self.loop.create_server(
            handler, '127.0.0.1', port)
        url = "http://127.0.0.1:{}".format(port)
        self.handler = handler
        self.srv = srv
        return app, srv, url

    def test_exceptions(self):

        @asyncio.coroutine
        def save(request):
            session = yield from get_session(request)
            session['message'] = 'works'
            raise web.HTTPFound('/show')

        @asyncio.coroutine
        def show(request):
            session = yield from get_session(request)
            message = session.get('message')
            return web.Response(text=str(message))

        def get_routes():
            return [
                ['GET', '/save', save],
                ['GET', '/show', show],
            ]

        @asyncio.coroutine
        def go():
            _, _, url = yield from self.create_server(get_routes())
            resp = yield from request('GET', url + '/save', loop=self.loop)
            self.assertEqual(200, resp.status)
            self.assertEqual(resp.url[-5:], '/show')
            text = yield from resp.text()
            assert text == 'works'

        self.loop.run_until_complete(go())
