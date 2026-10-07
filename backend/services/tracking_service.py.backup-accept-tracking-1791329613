from datetime import timezone
from sqlalchemy import select
from backend.models import DeliveryStatus, Restaurant, now
from backend.services.order_service import owned
from backend.services.delivery_service import location_for_order

RESTAURANT_STATES = {'PLACED','ACCEPTED','CONFIRMED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP','REJECTED'}
DRIVER_STATES = {'DRIVER_ASSIGNED','ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT','PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED'}

def states(db, order):
    history = list(db.scalars(select(DeliveryStatus).where(DeliveryStatus.order_id == order.id).order_by(DeliveryStatus.created_at, DeliveryStatus.id)))
    restaurant = 'PLACED'
    driver = 'DRIVER_ASSIGNED' if order.driver_id else None
    for event in history:
        if event.status in RESTAURANT_STATES:
            restaurant = event.status
        if event.status == 'DRIVER_REASSIGNED':
            driver = 'DRIVER_ASSIGNED'
        elif event.status in DRIVER_STATES:
            driver = event.status
    if order.status in RESTAURANT_STATES:
        restaurant = order.status
    if order.status in DRIVER_STATES:
        driver = order.status
    if order.status in {'CANCELLED','CANCELED','REJECTED'}:
        restaurant=order.status
        driver=order.status if order.driver_id else None
    if not order.driver_id:
        driver = None
    return restaurant, driver, history

def tracking(db, user, order_id):
    order = owned(db, user, order_id)
    restaurant_status, driver_status, history = states(db, order)
    restaurant = db.get(Restaurant, order.restaurant_id)
    location = location_for_order(db, user, order_id)
    if location:
        location['stale'] = (now() - location['updated_at']).total_seconds() > 30
        location['updated_at'] = location['updated_at'].replace(tzinfo=timezone.utc).isoformat()
    from backend.services.navigation_service import route
    navigation=route(order,restaurant,location,driver_status)
    return {
        'eta_seconds': navigation['eta_seconds'] if navigation else None,
        'route': navigation,
        'order_id': order.id, 'status': order.status, 'mode': order.mode,
        'restaurant_status': restaurant_status, 'driver_status': driver_status,
        'driver_id': order.driver_id, 'location': location,
        'restaurant': {'name': restaurant.name, 'address': restaurant.address, **((navigation or {}).get('restaurant_location') or {})},
        'customer_location': (navigation or {}).get('customer_location'),
        'destination': order.address,
        'history': [{'status': event.status, 'created_at': event.created_at.replace(tzinfo=timezone.utc).isoformat()} for event in history],
    }
