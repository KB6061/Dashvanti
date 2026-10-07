import json
import httpx
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

COOKIE = '__Host-dashvanti-social'
ALLOWED = {'social/config', 'social/challenge', 'google', 'facebook'}


@require_http_methods(['GET', 'POST'])
def social_proxy(request, path):
    if path not in ALLOWED:
        return JsonResponse({'detail': 'Not found'}, status=404)
    if not request.is_secure():
        return JsonResponse({'detail': 'HTTPS is required'}, status=400)
    expected_method = 'GET' if path == 'social/config' else 'POST'
    if request.method != expected_method:
        return JsonResponse({'detail': 'Method not allowed'}, status=405)
    headers = {'X-Forwarded-Proto': 'https', 'User-Agent': request.META.get('HTTP_USER_AGENT', '')[:500]}
    if request.headers.get('Origin'):
        headers['Origin'] = request.headers['Origin']
    if request.headers.get('X-Social-CSRF'):
        headers['X-Social-CSRF'] = request.headers['X-Social-CSRF']
    try:
        body = json.loads(request.body) if request.method == 'POST' else None
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            upstream = client.request(request.method, settings.API_URL.rstrip('/') + '/auth/' + path,
                headers=headers, cookies={COOKIE: request.COOKIES.get(COOKIE, '')}, json=body)
        data = upstream.json()
    except (ValueError, httpx.HTTPError):
        return JsonResponse({'detail': 'Sign-in service is temporarily unavailable'}, status=503)
    if upstream.is_success and path in {'google', 'facebook'} and data.get('two_factor_required'):
        request.session['account_2fa_challenge'] = data['challenge']
        request.session['account_2fa_provider'] = path
        return JsonResponse({'redirect_url': '/customer/account/verify-login'})
    if upstream.is_success and path in {'google', 'facebook'}:
        user = data['user']
        if user['role'] != 'customer':
            return JsonResponse({'detail': 'Use your driver or restaurant portal to sign in.'}, status=403)
        request.session.flush()
        request.session.update({'token': data['token'], 'role': user['role'],
            'name': user['name'], 'email': user['email'], 'user_id': user['id'],
            'social_login': True, 'auth_provider': user['provider'], 'order_mode': 'delivery', 'profile_photo': None})
        from common_app.api import call, APIError
        try:
            call(request, 'GET', '/me')
        except APIError as exc:
            request.session.flush()
            return JsonResponse({'detail': str(exc)}, status=exc.status)
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        data['redirect_url'] = '/customer/dashboard'
    response = JsonResponse(data, status=upstream.status_code)
    response['Cache-Control'] = 'no-store'
    if COOKIE in upstream.cookies:
        value = upstream.cookies.get(COOKIE)
        if value:
            response.set_cookie(COOKIE, value, max_age=300, secure=True,
                httponly=True, samesite='Lax', path='/')
        else:
            response.delete_cookie(COOKIE, path='/', samesite='Lax')
    return response
