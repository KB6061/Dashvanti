import json
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from backend.db import get_db, Session
from backend.security import admin_secret
from backend.payment_models import Payment, PaymentEvent
from backend.payment_schemas import SettingsInput, ToggleInput, RefundInput, SettlementInput, RestaurantCurrencyInput
from backend.services import admin_payment_service as service, phonepe_service
from backend.utils.payment_security import https_or_internal

router = APIRouter(prefix='/admin/payment', tags=['Admin payments'], dependencies=[Depends(https_or_internal), Depends(admin_secret)])


@router.get('/settings')
def settings(db=Depends(get_db, scope='function')):
    return service.settings_view(db)


@router.post('/settings/update')
def update(data: SettingsInput, db=Depends(get_db, scope='function')):
    return service.update_settings(db, data)


@router.post('/methods/toggle')
def toggle(data: ToggleInput, db=Depends(get_db, scope='function')):
    return service.toggle(db, data)


@router.get('/transactions')
def transactions(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), status: str | None = Query(None, max_length=24), db=Depends(get_db, scope='function')):
    return service.transactions(db, offset, limit, status)


@router.get('/transaction/{transaction_id}')
def transaction(transaction_id: int, db=Depends(get_db, scope='function')):
    return service.detail(db, transaction_id)


@router.post('/transaction/{transaction_id}/status')
def recheck(transaction_id: int, db=Depends(get_db, scope='function')):
    phonepe_service.recheck(db, service.transaction(db, transaction_id))
    return service.detail(db, transaction_id)


@router.post('/refund/{transaction_id}')
def refund(transaction_id: int, data: RefundInput, db=Depends(get_db, scope='function')):
    return phonepe_service.refund(db, service.transaction(db, transaction_id), data)


@router.post('/refund/{refund_id}/status')
def refund_status(refund_id: int, db=Depends(get_db, scope='function')):
    return phonepe_service.recheck_refund(db, refund_id)


@router.get('/settlements')
def settlements(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db=Depends(get_db, scope='function')):
    return service.settlements(db, offset, limit)


@router.post('/settlements/import')
def import_settlement(data: SettlementInput, db=Depends(get_db, scope='function')):
    return service.import_settlement(db, data)


@router.post('/restaurant-currency')
def currency(data: RestaurantCurrencyInput, db=Depends(get_db, scope='function')):
    return service.set_restaurant_currency(db, data)


@router.get('/logs')
def logs():
    def stream():
        yield '{"transactions":['
        with Session() as db:
            comma = ''
            for payment in db.scalars(select(Payment).order_by(Payment.id).execution_options(yield_per=100)):
                yield comma + json.dumps(jsonable_encoder(service.public_payment(db, payment)))
                comma = ','
            yield '],"events":['
            comma = ''
            for event in db.scalars(select(PaymentEvent).order_by(PaymentEvent.id).execution_options(yield_per=100)):
                yield comma + json.dumps(jsonable_encoder({'id': event.id, 'payment_id': event.payment_id, 'event': event.event, 'details': json.loads(event.details), 'created_at': event.created_at}))
                comma = ','
            yield ']}'
    return StreamingResponse(stream(), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="dashvanti-payment-logs.json"', 'Cache-Control': 'no-store'})
