from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import Order, Driver, Restaurant, DeliveryStatus, SystemConfig, now
from backend.models_driver_partner import DriverOffer
from backend.services.driver_partner_service import ensure_active, notice


def ensure_offer(db, order):
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update().execution_options(populate_existing=True))
    if not order: return None
    if order.driver_id or order.status not in {'ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP'}: return None
    offer = db.scalar(select(DriverOffer).where(DriverOffer.order_id == order.id, DriverOffer.status == 'OFFERED').with_for_update())
    if offer and offer.expires_at > now(): return offer
    if offer:
        offer.status = 'EXPIRED'
        key = f'driver-release:{order.id}:{offer.driver_id}'
        if not db.get(SystemConfig, key): db.add(SystemConfig(key=key, value='timeout'))
        db.flush()
    from backend.services.dispatch_service import nearby
    candidates = nearby(db, order, require_recent_gps=True, allow_active=True)
    for candidate in candidates:
        previous = db.scalar(select(DriverOffer.id).where(DriverOffer.order_id == order.id, DriverOffer.driver_id == candidate['id']))
        if previous: continue
        try: ensure_active(db, candidate['id'])
        except HTTPException: continue
        offer = DriverOffer(order_id=order.id, driver_id=candidate['id'], expires_at=now()+timedelta(seconds=30))
        db.add(offer); db.flush()
        from backend.services.operations_service import notify
        notify(db, candidate['id'], 'delivery-offer', f'Order #{order.id}: accept within 30 seconds.', order.id)
        notice(db, candidate['id'], 'ORDER_ASSIGNED', f'New delivery request #{order.id}. Open Dashvanti to accept or reject.')
        return offer
    return None


def validate_accept(db, driver_id, order_id):
    ensure_active(db, driver_id)
    row = db.scalar(select(DriverOffer).where(DriverOffer.driver_id == driver_id, DriverOffer.order_id == order_id).with_for_update())
    if not row or row.status != 'OFFERED' or row.expires_at <= now(): raise HTTPException(409, 'Delivery offer has expired or belongs to another driver')
    row.status = 'ACCEPTED'
    notice(db, driver_id, 'ORDER_ACCEPTED', f'You accepted order #{order_id}.')


def reject(db, driver_id, order_id):
    row = db.scalar(select(DriverOffer).where(DriverOffer.driver_id == driver_id, DriverOffer.order_id == order_id).with_for_update())
    if row and row.status == 'OFFERED': row.status = 'REJECTED'


def tick(db):
    from backend.services.restaurant_auto_accept_service import accept_pending
    accept_pending(db)
    rows = db.scalars(select(Order).where(Order.driver_id.is_(None), Order.mode == 'delivery', Order.status.in_(['ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP'])).order_by(Order.id).limit(100).with_for_update(skip_locked=True))
    for order in rows: ensure_offer(db, order)
