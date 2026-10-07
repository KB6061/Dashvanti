import json
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.models import Order, User, SystemConfig
from backend.payment_models import Payment, PaymentOrder, Refund
from backend.account_enhancement_models import WalletRefund
from backend.services.incident_service import permission
from backend.services.wallet_funding_service import refund_credit


def credit(db, admin, data):
    permission(db,admin,'gateway_edit')
    request=db.get(SystemConfig,data.refund_id)
    if not request:raise HTTPException(404,'Refund request not found')
    values=json.loads(request.value)
    order_id=values.get('order_id')
    payment=db.scalar(select(Payment).join(PaymentOrder,PaymentOrder.payment_id==Payment.id).where(PaymentOrder.order_id==order_id).with_for_update(of=Payment))
    order=db.scalar(select(Order).where(Order.id==order_id).with_for_update())
    request=db.scalar(select(SystemConfig).where(SystemConfig.key==data.refund_id).with_for_update().execution_options(populate_existing=True))
    values=json.loads(request.value)
    if values.get('status')=='WALLET_CREDITED':return {'message':'Refund already credited'}
    if values.get('status')!='PENDING' or not order or not payment or payment.status!='COMPLETED' or payment.environment!='production':
        raise HTTPException(409,'Wallet refunds require a pending request and a verified production payment')
    if payment.currency!=order.currency or db.get(WalletRefund,order.id):raise HTTPException(409,'Refund currency mismatch or order already credited')
    amount=Decimal(str(values.get('amount','0')))
    gateway_reserved=Decimal(db.scalar(select(func.coalesce(func.sum(Refund.amount),0)).where(Refund.payment_id==payment.id,Refund.status!='FAILED')))/100
    wallet_reserved=db.scalar(select(func.coalesce(func.sum(WalletRefund.amount),0)).where(WalletRefund.order_id.in_(select(PaymentOrder.order_id).where(PaymentOrder.payment_id==payment.id))))
    if amount<=0 or amount>order.total or amount+gateway_reserved+wallet_reserved>Decimal(payment.amount)/100:
        raise HTTPException(409,'Refund exceeds the remaining verified payment')
    db.add(WalletRefund(order_id=order.id,amount=amount,currency=order.currency,admin_id=admin.id,reason=data.reason))
    refund_credit(db,db.get(User,order.customer_id),order.currency,amount,data.refund_id)
    values.update(status='WALLET_CREDITED',payment_method='WALLET',admin_id=admin.id)
    request.value=json.dumps(values)
    db.info['audit_reason']=data.reason
    db.flush()
    return {'message':'Refund credited to customer wallet','order_id':order.id,'amount':amount,'currency':order.currency}
