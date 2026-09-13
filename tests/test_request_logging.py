import asyncio
import io
import logging
import time
import unittest
from frontend.common_app.logging_support import (
    CleanRequestFormatter, activity, client_ip, log_request, request_role,
)
from backend.request_logging import RequestLoggingMiddleware

class RequestLoggingTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.logger = logging.Logger('test', logging.INFO)
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(CleanRequestFormatter())
        self.logger.addHandler(handler)

    def test_format_excludes_sensitive_data(self):
        log_request(self.logger, '/customer/orders?token=secret', 200,
                    time.perf_counter(), '102', '192.168.56.1')
        text = self.output.getvalue()
        self.assertRegex(text, r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\]')
        self.assertIn('CUSTOMER REQUEST /customer/orders RESPONSE 200 Duration=', text)
        self.assertIn('UserID: 102\nIP: 192.168.56.1', text)
        self.assertIn('Activity: Customer viewing orders', text)
        self.assertNotIn('secret', text)
        self.assertEqual(len(text.splitlines()), 4)

    def test_levels(self):
        log_request(self.logger, '/driver/status/update', 200, time.perf_counter() - 2)
        log_request(self.logger, '/driver/status/update', 403, time.perf_counter())
        self.assertIn('[WARNING]', self.output.getvalue())
        self.assertIn('[ERROR]', self.output.getvalue())

    def test_roles_and_activity(self):
        for role in ('customer', 'restaurant', 'driver', 'admin'):
            self.assertEqual(request_role('/' + role + '/orders'), role.upper())
        self.assertEqual(request_role('/api/customer/orders'), 'SYSTEM')
        self.assertEqual(request_role('/administrator/orders'), 'SYSTEM')
        self.assertEqual(activity('/driver/location/update/'), 'Driver sending GPS update')

    def test_proxy_trust(self):
        self.assertEqual(client_ip('192.168.56.1', '1.2.3.4', []), '192.168.56.1')
        self.assertEqual(client_ip('127.0.0.1', '1.2.3.4, 10.0.0.8',
                                  ['127.0.0.1/32', '10.0.0.0/8']), '1.2.3.4')
        self.assertEqual(client_ip('127.0.0.1', 'invalid'), '127.0.0.1')

    def test_streaming_preserved_and_single_log(self):
        async def app(scope, receive, send):
            scope.setdefault('state', {})['log_user_id'] = 7
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'a', 'more_body': True})
            await send({'type': 'http.response.body', 'body': b'b'})
        events = []
        async def send(message):
            events.append(message)
        async def receive():
            return {'type': 'http.request', 'body': b''}
        middleware = RequestLoggingMiddleware(app)
        middleware.logger = self.logger
        asyncio.run(middleware({'type': 'http', 'path': '/driver/location/update',
                                'client': ('127.0.0.1', 1)}, receive, send))
        self.assertEqual([m.get('body') for m in events[1:]], [b'a', b'b'])
        self.assertEqual(self.output.getvalue().count('REQUEST'), 1)
        self.assertIn('UserID: 7', self.output.getvalue())

    def test_exception_is_preserved_without_secret(self):
        async def app(scope, receive, send):
            raise RuntimeError('private-token')
        middleware = RequestLoggingMiddleware(app)
        middleware.logger = self.logger
        with self.assertRaises(RuntimeError):
            asyncio.run(middleware({'type': 'http', 'path': '/customer/orders'}, None, None))
        self.assertIn('[ERROR]', self.output.getvalue())
        self.assertIn('RESPONSE 500', self.output.getvalue())
        self.assertNotIn('private-token', self.output.getvalue())

if __name__ == '__main__':
    unittest.main()
