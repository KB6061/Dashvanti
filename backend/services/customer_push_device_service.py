from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import delete, select
from backend.customer_push_models import CustomerPushDevice


def register(db, user, data):
    if user.role != 'customer':
        raise HTTPException(403, 'Customer account required')
    row = db.get(CustomerPushDevice, data.installation_id)
    if row and row.user_id != user.id:
        if row.token != data.token:
            raise HTTPException(409, 'Installation already registered')
        db.delete(row)
        db.flush()
        row = None
    other = db.scalar(select(CustomerPushDevice).where(CustomerPushDevice.token == data.token))
    if other and other.installation_id != data.installation_id:
        raise HTTPException(409, 'Push token already registered')
    if not row:
        row = CustomerPushDevice(installation_id=data.installation_id, user_id=user.id, token=data.token, token_version=user.token_version)
        db.add(row)
    if row.token_version != user.token_version:
        row.registered_at = datetime.utcnow()
    row.token = data.token
    row.token_version = user.token_version
    row.updated_at = datetime.utcnow()
    return {'registered': True}


def remove(db, user, installation_id):
    db.execute(delete(CustomerPushDevice).where(CustomerPushDevice.installation_id == installation_id, CustomerPushDevice.user_id == user.id))
    return {'removed': True}
