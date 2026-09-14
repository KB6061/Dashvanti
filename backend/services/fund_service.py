import json
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import SystemConfig, Order, AuditEvent

PREFIX = 'fund:'
KINDS = ('tax', 'service_fee', 'delivery_fee', 'discount', 'refund_limit', 'restaurant_commission')
def rules(db):
    return [dict(json.loads(row.value), kind=row.key[len(PREFIX):]) for row in db.scalars(select(SystemConfig).where(SystemConfig.key.like(PREFIX + '%')).order_by(SystemConfig.key))]

def save_rule(db, kind, data):
    if kind not in KINDS:
        raise HTTPException(422, 'Unknown fee type')
    if data.method == 'percent' and data.value > 100:
        raise HTTPException(422, 'Percentage cannot exceed 100')
    row = db.get(SystemConfig, PREFIX + kind)
    if row is None:
        row = SystemConfig(key=PREFIX + kind)
        db.add(row)
    row.value = data.model_dump_json()
    db.add(AuditEvent(action='fund-rule-updated', target=kind, details=row.value))
    db.flush()
    return dict(data.model_dump(), kind=kind)

def delete_rule(db, kind):
    row = db.get(SystemConfig, PREFIX + kind)
    if not row:
        raise HTTPException(404, 'Rule not found')
    db.delete(row)
    db.add(AuditEvent(action='fund-rule-deleted', target=kind, details='Rule removed; zero charge applies'))
    return {'deleted': kind}

def money(value):
    return Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def calculate(db, subtotal, mode, promo=Decimal('0')):
    configured = {row['kind']: row for row in rules(db)}
    def amount(kind):
        rule = configured.get(kind)
        if not rule or not rule['enabled']:
            return Decimal('0.00')
        value = Decimal(str(rule['value']))
        calculated = subtotal * value / 100 if rule['method'] == 'percent' else value
        return money(max(calculated, Decimal(str(rule['minimum']))))
    tax = amount('tax')
    service = amount('service_fee')
    delivery = amount('delivery_fee') if mode == 'delivery' else Decimal('0.00')
    discount = min(subtotal, max(amount('discount'), promo))
    return dict(subtotal=subtotal, tax=tax, service_fee=service, delivery_fee=delivery, discount=discount,
                total=money(subtotal + tax + service + delivery - discount))

def refunds(db):
    return [dict(json.loads(row.value), id=row.key) for row in db.scalars(select(SystemConfig).where(SystemConfig.key.like('refund:%')).order_by(SystemConfig.key.desc()))]

def request_refund(db, data):
    from uuid import uuid4
    order = db.scalar(select(Order).where(Order.id == data.order_id).with_for_update())
    if not order:
        raise HTTPException(404, 'Order not found')
    limit = next((r for r in rules(db) if r['kind'] == 'refund_limit' and r['enabled']), None)
    if not limit:
        raise HTTPException(409, 'Configure a refund limit first')
    maximum = min(order.total, money(order.total * Decimal(str(limit['value'])) / 100 if limit['method'] == 'percent' else limit['value']))
    previous = sum((Decimal(str(r['amount'])) for r in refunds(db) if r['order_id'] == order.id), Decimal('0'))
    if data.amount + previous > maximum:
        raise HTTPException(409, 'Refund exceeds the remaining permitted amount')
    key = 'refund:' + uuid4().hex
    payload = dict(order_id=order.id, customer_id=order.customer_id, amount=str(data.amount), reason=data.reason, status='PENDING')
    db.add(SystemConfig(key=key, value=json.dumps(payload)))
    db.add(AuditEvent(action='refund-requested', target=f'order:{order.id}', details=json.dumps(payload)))
    return dict(payload, id=key)

def edit_refund(db, refund_id, data):
    row = db.get(SystemConfig, refund_id)
    if refund_id.startswith('refund:cancellation:'):
        raise HTTPException(409, 'Cancellation refunds cannot be edited or deleted')
    if not row or not refund_id.startswith('refund:'):
        raise HTTPException(404, 'Refund request not found')
    existing = json.loads(row.value)
    db.scalar(select(Order).where(Order.id == existing['order_id']).with_for_update())
    if db.get(SystemConfig, f"cancellation:{existing['order_id']}"):
        raise HTTPException(409, 'Refunds committed to a cancellation cannot be changed')
    if existing.get('cancellation'):
        raise HTTPException(409, 'Cancellation refunds must be processed through the payment provider')
    if existing['status'] != 'PENDING':
        raise HTTPException(409, 'Only pending requests can be changed')
    if data.order_id != existing['order_id']:
        raise HTTPException(409, 'Cannot change the refund order')
    db.delete(row)
    db.flush()
    return request_refund(db, data)

def delete_refund(db, refund_id):
    row = db.get(SystemConfig, refund_id)
    if refund_id.startswith('refund:cancellation:'):
        raise HTTPException(409, 'Cancellation refunds cannot be edited or deleted')
    if not row or not refund_id.startswith('refund:'):
        raise HTTPException(404, 'Refund request not found')
    existing = json.loads(row.value)
    db.scalar(select(Order).where(Order.id == existing['order_id']).with_for_update())
    if db.get(SystemConfig, f"cancellation:{existing['order_id']}"):
        raise HTTPException(409, 'Refunds committed to a cancellation cannot be changed')
    if existing['status'] != 'PENDING':
        raise HTTPException(409, 'Only pending requests can be deleted')
    db.delete(row)
    db.add(AuditEvent(action='refund-request-deleted', target=refund_id, details='Pending request cancelled'))
    return {'deleted': refund_id}
