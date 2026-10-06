from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from backend.db import get_db
from backend.security import current_user
from backend.services import customer_push_device_service as service

router = APIRouter(prefix='/me', tags=['Customer push'])


class DeviceRegistration(BaseModel):
    installation_id: str = Field(min_length=36, max_length=64, pattern=r'^[a-zA-Z0-9-]+$')
    token: str = Field(min_length=20, max_length=4096)


@router.put('/push-device')
def register(data: DeviceRegistration, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return service.register(db, user, data)


@router.delete('/push-device')
def remove(installation_id: str, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return service.remove(db, user, installation_id)
