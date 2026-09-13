from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.security import role
from backend.presence_schemas import DriverPresence
from backend.services import presence_service

router = APIRouter(prefix='/driver', tags=['Driver availability'])
driver = role('driver')

@router.get('/presence')
def presence(user=Depends(driver), db=Depends(get_db, scope='function')):
    return presence_service.current(db, user)

@router.post('/presence')
def update_presence(data: DriverPresence, user=Depends(driver), db=Depends(get_db, scope='function')):
    return presence_service.update(db, user, data.mode)
