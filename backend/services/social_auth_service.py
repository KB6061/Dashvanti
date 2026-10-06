import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from urllib.parse import urlsplit
import httpx
import jwt
from fastapi import HTTPException
from google.auth.exceptions import TransportError
from backend.services.google_verification_transport import cached_request
from google.oauth2 import id_token
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, select
from backend.config import settings
from backend.models import Customer, User, now
from backend.social_config import social_settings as config
from backend.social_models import SocialChallenge, SocialIdentity
from backend.services.auth_service import passwords

email_adapter = TypeAdapter(EmailStr)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(db):
    db.execute(delete(SocialChallenge).where(SocialChallenge.expires_at < now()))
    csrf, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(SocialChallenge(digest=digest(csrf), nonce=nonce,
        expires_at=now() + timedelta(minutes=5), used_at=None))
    return csrf, nonce


def consume_challenge(db, csrf):
    row = db.scalar(select(SocialChallenge).where(
        SocialChallenge.digest == digest(csrf)).with_for_update())
    if not row or row.used_at or row.expires_at <= now():
        raise HTTPException(401, 'Login challenge expired. Reload and try again.')
    row.used_at = now()
    return row.nonce


def profile(provider, subject, name, email, picture):
    if not subject:
        raise HTTPException(401, 'Provider did not return a user identity')
    try:
        email = str(email_adapter.validate_python(email)).lower()
    except ValidationError:
        raise HTTPException(422, 'A valid email is required. Grant email access or use password login.')
    if not isinstance(picture, str) or urlsplit(picture).scheme != 'https':
        picture = None
    return {'provider': provider, 'provider_user_id': str(subject),
        'name': (name or email.split('@')[0])[:120], 'email': email,
        'profile_picture': picture[:2048] if picture else None}


def verify_google(token, nonce):
    try:
        claims = id_token.verify_oauth2_token(token, cached_request(), config.google_client_id)
    except TransportError:
        raise HTTPException(503, 'Google verification is temporarily unavailable')
    except ValueError:
        raise HTTPException(401, 'Invalid Google ID token')
    if claims.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}:
        raise HTTPException(401, 'Invalid Google issuer')
    if claims.get('email_verified') is not True:
        raise HTTPException(401, 'Google email is not verified')
    if not hmac.compare_digest(str(claims.get('nonce', '')), nonce):
        raise HTTPException(401, 'Google login nonce mismatch')
    return profile('google', claims.get('sub'), claims.get('name'),
        claims.get('email'), claims.get('picture'))


def graph_get(client, path, bearer, params):
    try:
        response = client.get(path, headers={'Authorization': 'Bearer ' + bearer}, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or 'error' in payload:
            raise ValueError()
        return payload
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500 or exc.response.status_code == 429:
            raise HTTPException(503, 'Facebook verification is temporarily unavailable')
        raise HTTPException(401, 'Invalid Facebook access token')
    except (httpx.RequestError, ValueError):
        raise HTTPException(503, 'Facebook verification is temporarily unavailable')


def verify_facebook(token):
    base = 'https://graph.facebook.com/' + config.facebook_graph_version + '/'
    app_token = config.facebook_app_id + '|' + config.facebook_app_secret
    with httpx.Client(base_url=base, timeout=10, follow_redirects=False) as client:
        data = graph_get(client, 'debug_token', app_token, {'input_token': token}).get('data', {})
        timestamp = int(time.time())
        if not isinstance(data, dict):
            raise HTTPException(401, 'Invalid Facebook token metadata')
        try:
            expires = int(data.get('expires_at', 0))
            data_expires = int(data.get('data_access_expires_at', 0))
        except (TypeError, ValueError):
            raise HTTPException(401, 'Invalid Facebook token expiry')
        if (data.get('is_valid') is not True
                or str(data.get('app_id')) != config.facebook_app_id
                or data.get('type') != 'USER'
                or not data.get('user_id')
                or expires <= timestamp
                or data_expires <= timestamp):
            raise HTTPException(401, 'Facebook token is expired or belongs to another app')
        proof = hmac.new(config.facebook_app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        user = graph_get(client, 'me', token,
            {'fields': 'id,name,email,picture.type(large)', 'appsecret_proof': proof})
    if str(user.get('id')) != str(data['user_id']):
        raise HTTPException(401, 'Facebook user identity mismatch')
    return profile('facebook', user.get('id'), user.get('name'), user.get('email'),
        user.get('picture', {}).get('data', {}).get('url'))


def authenticate(db, verified, link_user=None):
    identity = db.scalar(select(SocialIdentity).where(
        SocialIdentity.provider == verified['provider'],
        SocialIdentity.provider_user_id == verified['provider_user_id']).with_for_update())
    if identity:
        user = db.get(User, identity.user_id)
        if not user:
            raise HTTPException(401, 'Account is unavailable')
        if link_user and user.id != link_user.id:
            raise HTTPException(409, 'This social identity belongs to another account')
    else:
        if link_user:
            user = link_user
        else:
            if db.scalar(select(User.id).where(User.email == verified['email'])):
                raise HTTPException(409, 'Email already registered. Sign in with your existing account, then link this provider.')
            user = User(email=verified['email'], name=verified['name'], role='customer',
                password=passwords.hash(secrets.token_urlsafe(64)))
            db.add(user)
            db.flush()
            db.add(Customer(id=user.id))
        identity = SocialIdentity(user_id=user.id, provider=verified['provider'],
            provider_user_id=verified['provider_user_id'])
        db.add(identity)
    identity.profile_picture = verified['profile_picture']
    identity.last_login_at = now()
    # Keep the local email/name stable; provider subjects are the login identity.
    db.flush()
    issued = now()
    token = jwt.encode({'sub': str(user.id), 'ver': user.token_version, 'iat': issued,
        'exp': issued + timedelta(minutes=config.social_token_minutes),
        'iss': 'dashvanti-api', 'aud': 'dashvanti'}, settings.jwt_secret, algorithm='HS256')
    from backend.services.session_service import issue_tokens
    session_tokens = issue_tokens(user)
    return {**session_tokens, 'token': token, 'user': {'id': user.id, 'name': user.name,
        'email': user.email, 'role': user.role, 'provider': identity.provider,
        'provider_user_id': identity.provider_user_id,
        'profile_picture': identity.profile_picture,
        'last_login_at': identity.last_login_at.isoformat() + 'Z'}}
