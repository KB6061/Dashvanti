from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from backend.db import get_db
from backend.models import User
from backend.security import role
from backend.customer_account_schemas import AccountProfileInput, AccountActionInput, AccountTwoFactorInput
from backend.services import customer_account_service as service

router=APIRouter(tags=['Customer account'])
customer=role('customer')

@router.get('/customer/account')
def account(user=Depends(customer),db=Depends(get_db,scope='function')):
    return service.snapshot(db,user)

@router.put('/customer/account/profile')
def profile(data:AccountProfileInput,user=Depends(customer),db=Depends(get_db,scope='function')):
    return service.save_profile(db,user,data)

@router.post('/customer/account/action')
def action(data:AccountActionInput,user=Depends(customer),db=Depends(get_db,scope='function')):
    try:return service.action(db,user,data.action,data.data)
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'Check the required fields and try again')

@router.get('/customer/account/export')
def export(user=Depends(customer),db=Depends(get_db,scope='function')):
    return JSONResponse(jsonable_encoder(service.export(db,user)),headers={'Content-Disposition':'attachment; filename="dashvanti-account.json"','Cache-Control':'no-store'})

@router.post('/auth/account-2fa')
def verify(data:AccountTwoFactorInput,request:Request,db=Depends(get_db,scope='function')):
    return service.complete_second_factor(db,data,request)

@router.get('/admin/customers/{customer_id}/account')
def admin_account(customer_id:int,user=Depends(role('admin')),db=Depends(get_db,scope='function')):
    customer=db.get(User,customer_id)
    if not customer or customer.role!='customer':raise HTTPException(404,'Customer not found')
    return service.snapshot(db,customer)
