
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import Driver, DriverLocation, Order, Restaurant, User, Notification, DeliveryStatus, SystemConfig, now
from backend.services import eta_service
from backend.services.operations_service import notify, audit
from backend.services.kafka_event_service import emit

OPEN = {'ACCEPTED', 'PREPARING', 'PACKING', 'WRAPPING_UP', 'READY_FOR_PICKUP'}
BEFORE_PICKUP = OPEN | {'ON_THE_WAY_TO_RESTAURANT'}
FINAL = {'DELIVERED', 'REJECTED', 'CANCELLED', 'CANCELED'}
MAX_METERS = 3 * 1609.344

def eligible(db, driver_id, restaurant_id):
    driver = db.get(Driver, driver_id)
    location = db.get(DriverLocation, driver_id)
    if not driver or not driver.online or not location or location.updated_at < now() - timedelta(minutes=2):
        return None
    if db.scalar(select(Order.id).where(Order.driver_id == driver_id, Order.status.notin_(FINAL)).limit(1)):
        return None
    restaurant = db.get(Restaurant, restaurant_id)
    if not restaurant or not restaurant.address:
        return None
    try:
        travel = eta_service.route((location.latitude, location.longitude), restaurant.address)
    except HTTPException:
        return None
    if travel['distance_meters'] > MAX_METERS:
        return None
    user = db.get(User, driver_id)
    return {'id': driver_id, 'name': user.name, 'phone': user.phone,
            'distance_miles': travel['distance_miles'], 'drive_minutes': travel['drive_minutes']}

def nearby(db, order):
    if order.mode != 'delivery' or order.status not in BEFORE_PICKUP:
        return []
    candidates = []
    for driver_id in db.scalars(select(Driver.id).join(DriverLocation, DriverLocation.driver_id == Driver.id).where(Driver.online == True, DriverLocation.updated_at >= now() - timedelta(minutes=2))):
        if driver_id == order.driver_id or db.get(SystemConfig,f'driver-release:{order.id}:{driver_id}'):
            continue
        candidate = eligible(db, driver_id, order.restaurant_id)
        if candidate:
            candidates.append(candidate)
    return sorted(candidates, key=lambda row: (row['distance_miles'], row['drive_minutes']))

def offer(db, order, driver_id):
    existing = db.scalar(select(Notification.id).where(Notification.user_id == driver_id, Notification.order_id == order.id, Notification.kind == 'delivery-offer').limit(1))
    if not existing:
        notify(db, driver_id, 'delivery-offer', f'Order #{order.id} is available for pickup within 3 miles.', order.id)

def publish(db, order):
    for driver in nearby(db, order):
        offer(db, order, driver['id'])

def assigned(db, order, driver_id, previous=None):
    recipients = set(db.scalars(select(Notification.user_id).where(Notification.order_id == order.id, Notification.kind == 'delivery-offer')))
    for recipient in recipients - {driver_id}:
        notify(db, recipient, 'delivery-claimed', f'Order #{order.id} was accepted by another driver before you.', order.id)
    if previous:
        notify(db, previous, 'delivery-reassigned', f'Order #{order.id} was reassigned by admin. Do not pick up this order.', order.id)
    notify(db, driver_id, 'delivery-assigned', f'You are assigned to order #{order.id}.', order.id)
    notify(db, order.restaurant_id, 'driver-assigned', f'Delivery partner assigned to order #{order.id}.', order.id)

def reassign(db, order_id, driver_id, expected_driver_id, reason):
    driver = db.scalar(select(Driver).where(Driver.id == driver_id).with_for_update())
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, 'Order not found')
    if order.mode != 'delivery' or order.status not in BEFORE_PICKUP:
        raise HTTPException(409, 'Only orders waiting for pickup can be reassigned')
    if order.driver_id != expected_driver_id:
        raise HTTPException(409, 'Driver assignment changed. Refresh and try again')
    if not driver or not eligible(db, driver_id, order.restaurant_id):
        raise HTTPException(409, 'Driver must be available within 3 driving miles with recent GPS')
    previous = order.driver_id
    order.driver_id = driver_id
    if order.status == 'ON_THE_WAY_TO_RESTAURANT':
        order.status = 'READY_FOR_PICKUP'
    assigned(db, order, driver_id, previous)
    notify(db, order.customer_id, 'driver-reassigned', 'Admin assigned a new delivery partner to collect your order.', order.id)
    db.add(DeliveryStatus(order_id=order.id, status='DRIVER_REASSIGNED'))
    audit(db, None, 'driver-reassigned', f'order:{order.id}', f'{previous} -> {driver_id}. {reason}')
    emit(db, 'DRIVER_ASSIGNED', {'order_id': order.id, 'driver_id': driver_id})
    db.flush()
    return {'order_id': order.id, 'driver_id': driver_id}
