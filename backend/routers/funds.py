from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.security import admin_secret
from backend.schemas import FundRuleInput, RefundInput
from backend.services import fund_service
router = APIRouter(prefix='/operations/funds', dependencies=[Depends(admin_secret)])
@router.get('')
def listing(db=Depends(get_db, scope='function')):
    return {'rules': fund_service.rules(db), 'refunds': fund_service.refunds(db)}
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
