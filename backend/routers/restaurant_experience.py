from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from backend.db import get_db
from backend.security import optional_user, role
from backend.services import restaurant_experience_service as service

router = APIRouter()
customer = role('customer')

class PlanInput(BaseModel):
    scheduled_for: str | None = Field(default=None, max_length=50)

class GroupInput(BaseModel):
    restaurant_id: int = Field(gt=0)

class JoinInput(BaseModel):
    invite_code: str = Field(min_length=24, max_length=24, pattern=r'^[a-fA-F0-9]{24}$')

class ItemInput(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(ge=0, le=50)

@router.get('/restaurants/{restaurant_id}/experience')
def experience(restaurant_id: int, user=Depends(optional_user), db=Depends(get_db, scope='function')):
    return service.experience(db, restaurant_id, user)

@router.put('/restaurants/{restaurant_id}/schedule')
def schedule(restaurant_id: int, data: PlanInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.set_plan(db, user, restaurant_id, data.scheduled_for)

@router.get('/restaurants/{restaurant_id}/customer-photos')
def photos(restaurant_id: int, page: int = Query(1, ge=1), db=Depends(get_db, scope='function')):
    return service.customer_photos(db, restaurant_id, page)

@router.post('/group-orders', status_code=201)
def create(data: GroupInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.create_group(db, user, data.restaurant_id)

@router.post('/group-orders/join')
def join(data: JoinInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.join_group(db, user, data.invite_code)

@router.get('/group-orders/{group_id}')
def group(group_id: str, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.group_data(db, user, group_id)

@router.put('/group-orders/{group_id}/items')
def item(group_id: str, data: ItemInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.change_group(db, user, group_id, data.menu_item_id, data.quantity)

@router.post('/group-orders/{group_id}/checkout')
def checkout(group_id: str, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.finish_group(db, user, group_id)

@router.delete('/group-orders/{group_id}')
def remove(group_id: str, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.remove_group(db, user, group_id)
