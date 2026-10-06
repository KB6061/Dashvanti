import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.models import Order, OrderItem, SystemConfig, DeliveryStatus, AuditEvent, now
from backend.services.operations_service import notify, audit
from backend.services.order_service import owned

DEFAULT = {'preparation_percent':100,'review_threshold':3}
TERMINAL = {'DELIVERED','REJECTED','CANCELLED','CANCELED'}
AFTER_PICKUP = {'PICKED_UP','ON_THE_WAY_TO_CUSTOMER'}
PREPARING = {'PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP','ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT'}

def money(value):
    return Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def policy(db):
    row=db.get(SystemConfig,'cancellation:policy')
    return json.loads(row.value) if row else dict(DEFAULT)

def save_policy(db, data):
    row=db.get(SystemConfig,'cancellation:policy')
    if not row:
        row=SystemConfig(key='cancellation:policy',value='{}');db.add(row)
    row.value=json.dumps(data)
    audit(db,None,'cancellation-policy','funds',row.value)
    db.flush()
    return data

def snapshot(db, order):
    key=f'cancellation-policy:{order.id}'
    row=db.get(SystemConfig,key)
    if not row:
        row=SystemConfig(key=key,value=json.dumps(policy(db)));db.add(row);db.flush()
    return json.loads(row.value)

def quote(db, order, role, override=None):
    if order.status in TERMINAL:
        raise HTTPException(409,'Order is already completed or cancelled')
    if order.status in AFTER_PICKUP and role!='admin':
        raise HTTPException(409,'After pickup, contact support for cancellation review')
    if role=='driver':
        return {'order_id':order.id,'status':order.status,'action':'release','charge':'0.00','refund':'0.00','previous_refunds':'0.00'}
    rule=snapshot(db,order)
    subtotal=sum((item.price*item.quantity for item in db.scalars(select(OrderItem).where(OrderItem.order_id==order.id))),Decimal('0'))
    food=max(Decimal('0'),subtotal-(order.discount or Decimal('0')))
    charge=money(food*Decimal(str(rule['preparation_percent']))/100) if role=='customer' and order.status in PREPARING else Decimal('0.00')
    charge=min(charge,order.total)
    from backend.services.fund_service import refunds
    previous=sum((money(r['amount']) for r in refunds(db) if r['order_id']==order.id),Decimal('0'))
    remaining=max(Decimal('0'),order.total-previous)
    charge=min(charge,remaining)
    refund=min(remaining,max(Decimal('0'),order.total-charge-previous))
    if override is not None:
        if role!='admin' or money(override)<0 or money(override)>remaining:
            raise HTTPException(422,'Refund exceeds the remaining paid amount')
        refund=money(override);charge=max(Decimal('0'),order.total-previous-refund)
    return {'order_id':order.id,'status':order.status,'action':'cancel','charge':str(money(charge)),'refund':str(money(refund)),'previous_refunds':str(money(previous))}

def preview(db,user,order_id):
    order=owned(db,user,order_id,True)
    existing=db.get(SystemConfig,f'cancellation:{order.id}')
    return json.loads(existing.value) if existing else quote(db,order,user.role)

def cancel(db,user,order_id,data,admin=False):
    order=db.scalar(select(Order).where(Order.id==order_id).with_for_update()) if admin else owned(db,user,order_id,True)
    if not order:raise HTTPException(404,'Order not found')
    actor=None if admin else user.id
    role='admin' if admin else user.role
    key=f'cancellation:{order.id}'
    existing=db.get(SystemConfig,key)
    if existing:
        return json.loads(existing.value)
    result=quote(db,order,role,data.refund_override if admin else None)
    if result['status']!=data.expected_status or money(result['refund'])!=data.expected_refund or money(result['charge'])!=data.expected_charge:
        raise HTTPException(409,'Order changed. Review the updated cancellation amounts.')
    if role=='driver':
        db.add(SystemConfig(key=f'driver-release:{order.id}:{user.id}',value=json.dumps({'reason':data.reason,'at':now().isoformat()})))
        order.driver_id=None
        if order.status in {'ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT'}:order.status='READY_FOR_PICKUP'
        db.add(DeliveryStatus(order_id=order.id,status='DRIVER_RELEASED'))
        audit(db,actor,'driver-released',f'order:{order.id}',data.reason)
        notify(db,order.customer_id,'driver-reassignment','Finding another delivery partner for your order.',order.id)
        notify(db,order.restaurant_id,'driver-reassignment','Delivery partner released the order. Finding a replacement.',order.id)
        db.flush()
        from backend.services.dispatch_service import publish
        publish(db,order)
        flag_repeated(db,actor,role,order)
        return result
    driver_id=order.driver_id
    order.status='CANCELLED'
    result.update(reason=data.reason,actor_id=actor,actor_role=role,refund_status='PENDING' if money(result['refund']) else 'NOT_REQUIRED',created_at=now().isoformat())
    db.add(SystemConfig(key=key,value=json.dumps(result)))
    if money(result['refund']):
        refund={'order_id':order.id,'customer_id':order.customer_id,'amount':result['refund'],'reason':data.reason,'status':'PENDING','cancellation':True,'payment_method':'ORIGINAL'}
        db.add(SystemConfig(key=f'refund:cancellation:{order.id}',value=json.dumps(refund)))
    db.add(DeliveryStatus(order_id=order.id,status='CANCELLED'))
    audit(db,actor,'order-cancelled',f'order:{order.id}',json.dumps(result))
    for recipient in {order.customer_id,order.restaurant_id,driver_id}-{None}:
        notify(db,recipient,'order-cancelled',f'Order #{order.id} cancelled. Refund request: '+result['refund']+' USD.',order.id)
    db.flush()
    if actor is not None:
        flag_repeated(db,actor,role,order)
    return result

def flag_repeated(db,actor,role,order):
    db.flush()
    count=db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id==actor,AuditEvent.action.in_(['order-cancelled','driver-released']),AuditEvent.created_at>=now()-timedelta(days=30)))
    if count>=snapshot(db,order)['review_threshold']:
        audit(db,actor,'cancellation-review',f'{role}:{actor}','Repeated cancellations require review; no automatic penalty.')
