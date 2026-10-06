from fastapi import APIRouter, Depends, Header, HTTPException, Request
from backend.db import get_db
from backend.security import current_user, optional_bearer
from backend.schemas_driver_agreement import AgreementRead, AgreementAccept
from backend.services import driver_agreement_service as service

router = APIRouter(prefix='/driver/agreement', tags=['Driver agreement'])


def driver_or_guest(request: Request, credentials=Depends(optional_bearer), db=Depends(get_db, scope='function')):
    if not credentials: return None
    user = current_user(request, credentials, db)
    if user.role != 'driver': raise HTTPException(403, 'Driver agreement is for driver onboarding only.')
    return user


@router.get('')
def agreement():
    return service.payload()


@router.post('/session', status_code=201)
def start(user=Depends(driver_or_guest), db=Depends(get_db, scope='function')):
    return service.start(db, user)


@router.get('/status')
def status(token: str | None = Header(None, alias='X-Driver-Agreement-Token'), user=Depends(driver_or_guest), db=Depends(get_db, scope='function')):
    return service.status(db, token, user)


@router.post('/read')
def read(data: AgreementRead, token: str | None = Header(None, alias='X-Driver-Agreement-Token'), user=Depends(driver_or_guest), db=Depends(get_db, scope='function')):
    return service.record_read(db, token, data, user)


@router.post('/accept')
def accept(data: AgreementAccept, request: Request, token: str | None = Header(None, alias='X-Driver-Agreement-Token'), user=Depends(driver_or_guest), db=Depends(get_db, scope='function')):
    return service.accept(db, token, data, service.request_context(request), user)


@router.post('/decline')
def decline(token: str | None = Header(None, alias='X-Driver-Agreement-Token'), user=Depends(driver_or_guest), db=Depends(get_db, scope='function')):
    return service.decline(db, token, user)
