import jwt
from datetime import timedelta
from fastapi import HTTPException
from backend.config import settings
from backend.models import User, now

def issue_tokens(user):
    issued = now()
    claims = {'sub': str(user.id), 'ver': user.token_version, 'iat': issued, 'iss': 'dashvanti-api'}
    access = jwt.encode({**claims, 'exp': issued + timedelta(hours=2), 'aud': 'dashvanti'}, settings.jwt_secret, algorithm='HS256')
    refresh = jwt.encode({**claims, 'aud': 'dashvanti-session', 'kind': 'persistent-session'}, settings.jwt_secret, algorithm='HS256')
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer', 'role': user.role}

def refresh_session(db, token):
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'], audience='dashvanti-session', issuer='dashvanti-api', options={'require': ['sub', 'ver', 'iat', 'kind']})
        if claims['kind'] != 'persistent-session':
            raise ValueError()
        user = db.get(User, int(claims['sub']))
        if not user or user.token_version != claims['ver']:
            raise ValueError()
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, 'Session revoked')
    return issue_tokens(user)
