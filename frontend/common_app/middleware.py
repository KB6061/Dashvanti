import time
from common_app.logging_support import client_ip, configure_logging, log_request, user_id

from django.conf import settings
from django.http import HttpResponseNotFound
from django.shortcuts import redirect


class PortalScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.portal = getattr(settings, 'PORTAL_ROLE', '')

    def __call__(self, request):
        if self.portal and not request.path.startswith('/static/'):
            response = self._scope_response(request)
            if response is not None:
                return response
        return self.get_response(request)

    def _scope_response(self, request):
        if request.path in {'/favicon.ico'}:
            return None
        if request.path == '/':
            if self.portal == 'customer':
                return redirect('/customer/restaurants' if request.session.get('token') and request.session.get('role') == 'customer' else '/customer/login')
            if self.portal in {'restaurant', 'driver'}:
                return redirect(f'/{self.portal}/dashboard' if request.session.get('token') and request.session.get('role') == self.portal else f'/{self.portal}/login')
            if self.portal == 'admin':
                return redirect('/admin/dashboard' if request.session.get('admin_authenticated') else '/admin/login')
        if self.portal in {'customer', 'restaurant', 'driver'}:
            if request.path.startswith(f'/{self.portal}/'):
                return None
            return HttpResponseNotFound('Portal not available on this port')
        if self.portal == 'admin':
            if request.path.startswith('/admin/'):
                return None
            return HttpResponseNotFound('Portal not available on this port')
        return None


class UIActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = configure_logging(
            'dashvanti.portal.requests', getattr(settings, 'DJANGO_ACTIVITY_LOG', None)
        )

    def __call__(self, request):
        started = time.perf_counter()
        status = 500
        failed = False
        identity = self._identity(request)
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        except Exception:
            failed = True
            raise
        finally:
            session = getattr(request, 'session', {})
            log_request(
                self.logger, request.path, status, started,
                getattr(request, '_log_identity', identity) if getattr(request, '_log_identity', identity) != '-' else self._identity(request),
                client_ip(request.META.get('REMOTE_ADDR', '-'),
                          request.META.get('HTTP_X_FORWARDED_FOR', '')),
                failed, request.method, {
                    'user_name': session.get('name', '-'),
                    'phone': session.get('phone', '-'),
                    'device': request.META.get('HTTP_X_DEVICE', '-'),
                    'app_version': request.META.get('HTTP_X_APP_VERSION', '-'),
                    'geo': request.META.get('HTTP_X_GEO', '-'),
                    'correlation_id': request.META.get('HTTP_X_CORRELATION_ID', ''),
                    'request_id': request.META.get('HTTP_X_REQUEST_ID', ''),
                },
            )

    def process_view(self, request, view_func, view_args, view_kwargs):
        request._log_identity = self._identity(request)

    @staticmethod
    def _identity(request):
        session = getattr(request, 'session', {})
        if session.get('token') or session.get('admin_authenticated'):
            return user_id(session.get('user_id'))
        return '-'
