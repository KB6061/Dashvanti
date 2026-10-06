from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.security import admin_secret
from backend.schemas import FundRuleInput, RefundInput, QuickPayInput
from backend.services import fund_service, revenue_service
router = APIRouter(prefix='/operations/funds', dependencies=[Depends(admin_secret)])
@router.get('')
def listing(db=Depends(get_db, scope='function')):
    return {'rules': fund_service.rules(db), 'refunds': fund_service.refunds(db)}

@router.get('/revenue')
def revenue(date_range: str = '', start_date: str = '', end_date: str = '', restaurant_id: str = '', driver_id: str = '', payment_mode: str = '', status: str = '', q: str = '', db=Depends(get_db, scope='function')):
    return revenue_service.revenue_report(db, {
        'date_range': date_range, 'start_date': start_date, 'end_date': end_date,
        'restaurant_id': restaurant_id, 'driver_id': driver_id, 'payment_mode': payment_mode,
        'status': status, 'q': q,
    })

@router.post('/quick-pay', status_code=201)
def quick_pay(data: QuickPayInput, db=Depends(get_db, scope='function')):
    return revenue_service.quick_pay(db, data.order_id, data.payee_role)
@router.put('/rules/{kind}')
def save(kind: str, data: FundRuleInput, db=Depends(get_db, scope='function')):
    return fund_service.save_rule(db, kind, data)
@router.delete('/rules/{kind}')
def delete(kind: str, db=Depends(get_db, scope='function')):
    return fund_service.delete_rule(db, kind)
@router.post('/refunds', status_code=201)
def refund(data: RefundInput, db=Depends(get_db, scope='function')):
    return fund_service.request_refund(db, data)

@router.put('/refunds/{refund_id}')
def edit_refund(refund_id: str, data: RefundInput, db=Depends(get_db, scope='function')):
    return fund_service.edit_refund(db, refund_id, data)
@router.delete('/refunds/{refund_id}')
def delete_refund(refund_id: str, db=Depends(get_db, scope='function')):
    return fund_service.delete_refund(db, refund_id)
