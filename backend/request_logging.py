import logging
import time
from frontend.common_app.logging_support import client_ip, configure_logging, log_request

class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app
        self.logger = configure_logging('dashvanti.api.requests')
        logging.getLogger('uvicorn.access').disabled = True

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 500
        failed = False
        headers = dict(scope.get('headers', ()))
        peer = (scope.get('client') or ('-', 0))[0]
        ip = client_ip(peer, headers.get(b'x-forwarded-for', b'').decode('latin-1'))

        async def capture(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        except Exception:
            failed = True
            raise
        finally:
            state = scope.get('state', {})
            identity = state.get('log_user_id', '-')
            headers_text = {k.decode('latin-1'): v.decode('latin-1') for k, v in headers.items()}
            log_request(self.logger, scope.get('path', '/'), status, started,
                        identity, ip, failed, scope.get('method', 'REQUEST'), {
                            'user_name': state.get('log_user_name', '-'),
                            'phone': state.get('log_user_phone', '-'),
                            'device': headers_text.get('x-device', '-'),
                            'app_version': headers_text.get('x-app-version', '-'),
                            'geo': headers_text.get('x-geo', '-'),
                            'correlation_id': headers_text.get('x-correlation-id', ''),
                            'request_id': headers_text.get('x-request-id', ''),
                        })
