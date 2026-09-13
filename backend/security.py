import secrets
import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.config import settings
from backend.db import get_db
from backend.models import User

bearer = HTTPBearer()

def current_user(request: Request, auth: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db, scope='function')):
    try:
        claims = jwt.decode(auth.credentials, settings.jwt_secret, algorithms=['HS256'], audience='dashvanti', issuer='dashvanti-api', options={'require': ['exp','iat','sub','ver']})
        user = db.get(User, int(claims['sub']))
        if not user or user.token_version != claims['ver']:
            raise ValueError()
        request.state.log_user_id = user.id
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, 'Session expired')

def role(*allowed):
    def check(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, 'Forbidden')
        return user
    return check


def admin_secret(value: str = Header(default='', alias='X-Dashvanti-Admin-Secret')):
    if not settings.admin_secret or not secrets.compare_digest(value, settings.admin_secret):
        raise HTTPException(403, 'Forbidden')
