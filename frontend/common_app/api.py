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

def call(request, method, path, data=None, params=None, files=None, raw=False):
    try:
        renew_session(request)
    except (httpx.HTTPError, ValueError):
        raise APIError('Service temporarily unavailable. Please try again.',503)
    headers = {'Authorization':'Bearer '+request.session['token']} if request.session.get('token') else {}
    headers['Cookie'] = ''
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
