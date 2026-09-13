from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.schemas import Register, Login, Forgot, Reset
from backend.security import current_user
from backend.services import auth_service as service

router = APIRouter(prefix='/auth', tags=['Authentication'])

@router.post('/register', status_code=201)
def register(data: Register, db=Depends(get_db, scope='function')):
    return service.register(db, data)

@router.post('/login')
def login(data: Login, db=Depends(get_db, scope='function')):
    return service.login(db, data)

@router.post('/forgot')
def forgot(data: Forgot, db=Depends(get_db, scope='function')):
    return service.forgot(db, data)

@router.post('/reset')
def reset(data: Reset, db=Depends(get_db, scope='function')):
    return service.reset(db, data)

@router.post('/logout')
def logout(user=Depends(current_user), db=Depends(get_db, scope='function')):
    user.token_version += 1
    return {'message':'Logged out'}

from backend.session_schemas import SessionRefresh
from backend.services.session_service import issue_tokens, refresh_session

@router.post('/session')
def persistent_session(user=Depends(current_user)):
    return issue_tokens(user)

@router.post('/refresh')
def refresh(data: SessionRefresh, db=Depends(get_db, scope='function')):
    return refresh_session(db, data.refresh_token)
