from fastapi import APIRouter, Depends, Response, HTTPException
from backend.db import get_db
from backend.security import current_user, admin_secret
from backend.models import Order
from backend.schemas import CancellationInput, CancellationPolicyInput
from backend.services import cancellation_service as service

router=APIRouter()

@router.get('/orders/{order_id}/cancellation')
def preview(order_id:int,response:Response,user=Depends(current_user),db=Depends(get_db,scope='function')):
    response.headers['Cache-Control']='no-store'
    return service.preview(db,user,order_id)

@router.post('/orders/{order_id}/cancellation')
def cancel(order_id:int,data:CancellationInput,user=Depends(current_user),db=Depends(get_db,scope='function')):
    return service.cancel(db,user,order_id,data)

@router.get('/operations/cancellation-policy',dependencies=[Depends(admin_secret)])
def policy(db=Depends(get_db,scope='function')):
    return service.policy(db)

@router.put('/operations/cancellation-policy',dependencies=[Depends(admin_secret)])
def save_policy(data:CancellationPolicyInput,db=Depends(get_db,scope='function')):
    return service.save_policy(db,data.model_dump())

@router.get('/operations/orders/{order_id}/cancellation',dependencies=[Depends(admin_secret)])
def admin_preview(order_id:int,db=Depends(get_db,scope='function')):
    order=db.get(Order,order_id)
    if not order:raise HTTPException(404,'Order not found')
    return service.quote(db,order,'admin')

@router.post('/operations/orders/{order_id}/cancellation',dependencies=[Depends(admin_secret)])
def admin_cancel(order_id:int,data:CancellationInput,db=Depends(get_db,scope='function')):
    return service.cancel(db,None,order_id,data,True)

@router.get('/cancellation-policy')
def customer_policy(user=Depends(current_user),db=Depends(get_db,scope='function')):
    return service.policy(db)
