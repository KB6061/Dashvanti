import hmac
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from backend.db import get_db
from backend.security import current_user
from backend.social_config import social_settings as config
from backend.social_schemas import FacebookLogin, GoogleLogin
from backend.services import social_auth_service as service

router = APIRouter(prefix='/auth', tags=['Social authentication'])
COOKIE = '__Host-dashvanti-social'


def https_only(request: Request):
    if request.url.scheme != 'https':
        raise HTTPException(400, 'HTTPS is required')


def login_guard(request, csrf):
    https_only(request)
    if request.headers.get('origin') != config.social_origin:
        raise HTTPException(403, 'Untrusted login origin')
    cookie = request.cookies.get(COOKIE, '')
    header = request.headers.get('x-social-csrf', '')
    if not cookie or not header or not hmac.compare_digest(cookie, csrf) or not hmac.compare_digest(header, csrf):
        raise HTTPException(403, 'Login CSRF check failed')


def require_provider(provider):
    ready = bool(config.google_client_id) if provider == 'google' else bool(
        config.facebook_app_id and config.facebook_app_secret and config.facebook_graph_version)
    if not ready:
        raise HTTPException(503, provider.title() + ' sign-in is not configured yet. Continue with Email.')


def finish(response, result):
    response.headers['Cache-Control'] = 'no-store'
    response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='lax')
    return result


@router.get('/social/config')
def public_config(request: Request):
    https_only(request)
    return {'google_client_id': config.google_client_id,
        'facebook_app_id': config.facebook_app_id,
        'facebook_graph_version': config.facebook_graph_version,
        'google_enabled': bool(config.google_client_id),
        'facebook_enabled': bool(config.facebook_app_id and config.facebook_app_secret and config.facebook_graph_version)}


@router.post('/social/challenge')
def challenge(request: Request, response: Response, db=Depends(get_db, scope='function')):
    https_only(request)
    if request.headers.get('origin') != config.social_origin:
        raise HTTPException(403, 'Untrusted login origin')
    csrf, nonce = service.challenge(db)
    response.set_cookie(COOKIE, csrf, max_age=300, secure=True, httponly=True, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'csrf_token': csrf, 'nonce': nonce}


@router.post('/google')
def google_login(data: GoogleLogin, request: Request, response: Response,
        db=Depends(get_db, scope='function')):
    require_provider('google')
    login_guard(request, data.csrf_token)
    nonce = service.consume_challenge(db, data.csrf_token)
    verified = service.verify_google(data.id_token, nonce)
    return finish(response, service.authenticate(db, verified, request=request))


@router.post('/facebook')
def facebook_login(data: FacebookLogin, request: Request, response: Response,
        db=Depends(get_db, scope='function')):
    require_provider('facebook')
    login_guard(request, data.csrf_token)
    service.consume_challenge(db, data.csrf_token)
    verified = service.verify_facebook(data.access_token)
    return finish(response, service.authenticate(db, verified, request=request))


@router.post('/link/google')
def link_google(data: GoogleLogin, request: Request, response: Response,
        user=Depends(current_user), db=Depends(get_db, scope='function')):
    require_provider('google')
    login_guard(request, data.csrf_token)
    nonce = service.consume_challenge(db, data.csrf_token)
    return finish(response, service.authenticate(db, service.verify_google(data.id_token, nonce), user))


@router.post('/link/facebook')
def link_facebook(data: FacebookLogin, request: Request, response: Response,
        user=Depends(current_user), db=Depends(get_db, scope='function')):
    require_provider('facebook')
    login_guard(request, data.csrf_token)
    service.consume_challenge(db, data.csrf_token)
    return finish(response, service.authenticate(db, service.verify_facebook(data.access_token), user))
