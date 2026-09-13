from fastapi import HTTPException
from sqlalchemy import select
from backend.models import DeliveryStatus
from backend.services import eta_service
from backend.services.operations_service import notify

def detect(db, order, latitude, longitude):
    if order.mode != 'delivery' or order.status != 'ON_THE_WAY_TO_CUSTOMER':
        return False
    if db.scalar(select(DeliveryStatus.id).where(DeliveryStatus.order_id == order.id, DeliveryStatus.status == 'ARRIVED_AT_CUSTOMER')):
        return False
    try:
        distance = eta_service.route((latitude, longitude), order.address)['distance_meters']
    except HTTPException:
        return False
    if distance > 50:
        return False
    db.add(DeliveryStatus(order_id=order.id, status='ARRIVED_AT_CUSTOMER'))
    notify(db, order.customer_id, 'driver-arrived', 'Your delivery partner has arrived at your address.', order.id)
    db.flush()
    return True
