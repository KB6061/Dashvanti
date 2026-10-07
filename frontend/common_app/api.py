import atexit
import time
import jwt
from functools import lru_cache
import httpx
from django.conf import settings

class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

@lru_cache(maxsize=1)
def api_client():
    client = httpx.Client(timeout=20, trust_env=False, limits=httpx.Limits(max_connections=32, max_keepalive_connections=16))
    atexit.register(client.close)
    return client

def renew_session(request):
    session = request.session
    token = session.get('token')
    if not token:
        return
    try:
        expiry = jwt.decode(token, options={'verify_signature': False}).get('exp', 0)
    except jwt.PyJWTError:
        return
    try:
        expiry = float(expiry)
    except (TypeError, ValueError):
        return
    refresh = session.get('refresh_token')
    if refresh and float(expiry) > time.time() + 120:
        return
    path = '/auth/refresh' if refresh else '/auth/session'
    headers = {'Cookie': ''}
    if not refresh:
        headers['Authorization'] = 'Bearer ' + token
    response = api_client().post(settings.API_URL + path, headers=headers,
                                 json={'refresh_token': refresh} if refresh else {})
    if response.is_success:
        result = response.json()
        session['token'] = result['access_token']
        session['refresh_token'] = result['refresh_token']
    elif response.status_code in {401, 403}:
        raise APIError('Session expired', 401)
    else:
        raise APIError('Service temporarily unavailable. Please try again.', 503)

def call(request, method, path, data=None, params=None, files=None, raw=False):
    public_auth = path.startswith('/auth/') and path.rsplit('/', 1)[-1] in {'login', 'register', 'forgot', 'reset', 'account-2fa'}
    try:
        if not public_auth:
            renew_session(request)
    except (httpx.HTTPError, ValueError):
        raise APIError('Service temporarily unavailable. Please try again.',503)
    if not public_auth and not request.session.get('token'):
        raise APIError('Session expired', 401)
    headers = {'Authorization':'Bearer '+request.session['token']} if request.session.get('token') else {}
    headers['Cookie'] = ''
    headers['User-Agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]
    if path.startswith(('/payment/', '/phonepe/')):
        import hashlib, hmac, os
        key = os.environ.get('PAYMENT_PROXY_SECRET', '')
        peer = request.META.get('REMOTE_ADDR', '')
        address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[-1].strip() if peer in {'127.0.0.1', '::1'} else peer
        if key and address:
            timestamp = str(int(time.time()))
            headers.update({'X-Dashvanti-Client-IP': address, 'X-Dashvanti-IP-Time': timestamp,
                'X-Dashvanti-IP-Signature': hmac.new(key.encode(), f'{timestamp}:{address}'.encode(), hashlib.sha256).hexdigest()})

    try:
        response = api_client().request(method, settings.API_URL+path, headers=headers, params=params, **({'files':files,'data':data} if files else {'json':data}))
        if response.is_error:
            detail = response.json().get('detail','Request failed')
            if isinstance(detail,list):
                detail = '; '.join(str(e.get('loc', ['field'])[-1])+': '+e['msg'] for e in detail)
            raise APIError(str(detail),response.status_code)
        return response if raw else response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise APIError('Service temporarily unavailable. Please try again.',503) from exc
