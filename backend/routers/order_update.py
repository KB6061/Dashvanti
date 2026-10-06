from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from backend.db import get_db
from backend.security import role
from backend.services.delivery_service import transition

router = APIRouter(tags=['Order updates'])


class OrderUpdate(BaseModel):
    order_id: int = Field(gt=0)
    status: str = Field(max_length=40)


@router.post('/order/update')
def update(data: OrderUpdate, user=Depends(role('restaurant', 'driver')), db=Depends(get_db, scope='function')):
    aliases = {'READY': 'READY_FOR_PICKUP', 'DELIVERING': 'ON_THE_WAY_TO_CUSTOMER', 'COMPLETED': 'DELIVERED'}
    return transition(db, user, data.order_id, aliases.get(data.status.upper(), data.status.upper()))
