from sqlalchemy import select
from backend.models import Driver, User, DeliveryStatus
from backend.models_driver_queue import DriverUpcomingOrder
from backend.services.driver_queue_service import active_orders, FINAL


def state(db, order):
    if order.status in FINAL or order.mode != 'delivery':
        return None
    reservation = db.scalar(select(DriverUpcomingOrder).where(DriverUpcomingOrder.order_id == order.id))
    driver_id = reservation.driver_id if reservation else order.driver_id
    if not driver_id:
        return None
    from backend.services.tracking_service import states
    if reservation:
        current = active_orders(db, driver_id)
        driver_status = states(db, current[0])[1] if current else None
        if driver_status in {'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER', 'ARRIVED_AT_CUSTOMER'}:
            phase = 'delivering_other_orders'
            message = 'Your driver is on the way and delivering another order. They will head to the restaurant to pick up your order next.'
        elif current:
            phase = 'picking_up_other_order'
            message = 'Your driver has an existing order and is picking it up. They will then head to the restaurant to pick up your order.'
        else:
            phase = 'waiting_for_previous_delivery'
            message = 'Your driver has accepted your upcoming order and will head to the restaurant to pick it up next.'
    else:
        was_queued = db.scalar(select(DeliveryStatus.id).where(DeliveryStatus.order_id == order.id, DeliveryStatus.status == 'DRIVER_QUEUED').limit(1))
        if not was_queued:
            return None
        driver_status = states(db, order)[1]
        if driver_status in {'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER'}:
            phase = 'heading_to_customer'
            message = 'Your driver is heading to you to deliver your order.'
        elif driver_status == 'ARRIVED_AT_CUSTOMER':
            phase = 'arrived_at_customer'
            message = 'Your driver has arrived with your order.'
        else:
            phase = 'heading_to_pickup'
            message = 'Your driver has finished the other delivery and is heading to the restaurant to pick up your order.'
    profile = db.get(Driver, driver_id)
    user = db.get(User, driver_id)
    if reservation and (not profile or not profile.online):
        phase = 'waiting_for_driver'
        message = 'Your reserved driver is offline. Waiting for a delivery partner to continue your order.'
    return {'queued': bool(reservation), 'phase': phase, 'message': message,
        'driver': {'id': driver_id, 'name': user.name if user else '', 'phone': user.phone if user else '',
            'vehicle_type': profile.vehicle_type if profile else '', 'vehicle_number': profile.vehicle_number if profile else ''}}
