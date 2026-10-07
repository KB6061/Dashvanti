from fastapi import APIRouter, BackgroundTasks, Depends, Request
from backend.db import get_db
from backend.security import role, admin_secret
from backend.payment_schemas import PayInput, StatusInput, RefundWithPayment, CountryInput
from backend.services import phonepe_service as service
from backend.services import admin_payment_service as admin
from backend.services.geo_service import normalize_country
from backend.utils.payment_security import https_or_internal

router = APIRouter(tags=['Payments'], dependencies=[Depends(https_or_internal)])
customer = role('customer')


@router.get('/payment/methods')
def payment_methods(request: Request, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.methods(db, request, user)


@router.put('/payment/country')
def country(data: CountryInput, user=Depends(customer)):
    from fastapi import HTTPException
    value = normalize_country(data.country)
    if not value:
        raise HTTPException(400, 'Use India or a two-letter country code')
    if user.country != value:
        from fastapi import HTTPException
        raise HTTPException(422,'Country is determined by your delivery address. Update the address first.')
    user.country = value
    return {'country': value}


@router.post('/phonepe/pay')
def pay(data: PayInput, request: Request, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.pay(db, request, user, data)


@router.post('/phonepe/status')
def status(data: StatusInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    payment = service.payment_owned(db, data.transaction_id, user)
    service.recheck(db, payment)
    return admin.public_payment(db, payment)


@router.get('/phonepe/transaction/{transaction_id}')
def transaction(transaction_id: int, user=Depends(customer), db=Depends(get_db, scope='function')):
    return service.payment_result(db, service.payment_owned(db, transaction_id, user))


@router.post('/phonepe/refund', dependencies=[Depends(admin_secret)])
def refund(data: RefundWithPayment, db=Depends(get_db, scope='function')):
    return service.refund(db, admin.transaction(db, data.transaction_id), data)


@router.post('/phonepe/callback')
async def callback(request: Request, tasks: BackgroundTasks, db=Depends(get_db, scope='function')):
    from backend.services.wallet_webhook_service import phonepe_funding,read_body
    raw=await read_body(request)
    wallet_result=phonepe_funding(db,raw,request.headers)
    if wallet_result is not None:return {'received':True,**wallet_result}
    payment_id, refund_id = service.receive_callback(db,raw,request.headers)
    tasks.add_task(service.reconcile, payment_id, refund_id)
    return {'received': True}
