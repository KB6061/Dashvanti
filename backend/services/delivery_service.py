from datetime import timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.models import Order, OrderItem, Driver, DriverLocation, DeliveryStatus, Restaurant, User, SystemConfig, PayoutTransaction, now
from backend.services.order_service import owned
from backend.services.kafka_event_service import emit

RESTAURANT_TRANSITIONS = {'PLACED': ['ACCEPTED','CONFIRMED','REJECTED'], 'ACCEPTED': ['PREPARING'], 'CONFIRMED': ['PREPARING'], 'PREPARING': ['PACKING','READY_FOR_PICKUP'], 'PACKING': ['WRAPPING_UP','READY_FOR_PICKUP'], 'WRAPPING_UP': ['READY_FOR_PICKUP'], 'READY_FOR_PICKUP': ['DELIVERED']}
DRIVER_TRANSITIONS = {'READY_FOR_PICKUP': ['ON_THE_WAY_TO_RESTAURANT'], 'ON_THE_WAY_TO_RESTAURANT': ['PICKED_UP'], 'PICKED_UP': ['ON_THE_WAY_TO_CUSTOMER'], 'ON_THE_WAY_TO_CUSTOMER': ['DELIVERED']}
EVENTS = {'ACCEPTED':'ORDER_ACCEPTED','CONFIRMED':'ORDER_ACCEPTED','REJECTED':'ORDER_REJECTED','PREPARING':'ORDER_PREPARING','READY_FOR_PICKUP':'ORDER_READY_FOR_PICKUP','PICKED_UP':'ORDER_PICKED_UP','DELIVERED':'ORDER_DELIVERED'}

def transition(db, user, order_id, status):
    order = owned(db, user, order_id, True)
    from backend.services.tracking_service import states
    restaurant_status, driver_status, _ = states(db, order)
    if user.role == 'driver':
        driver_allowed = {
            'DRIVER_ASSIGNED': ['ON_THE_WAY_TO_RESTAURANT'],
            'ON_THE_WAY_TO_RESTAURANT': ['ARRIVED_AT_RESTAURANT','PICKED_UP'],
            'ARRIVED_AT_RESTAURANT': ['PICKED_UP'],
            'PICKED_UP': ['ON_THE_WAY_TO_CUSTOMER'],
            'ON_THE_WAY_TO_CUSTOMER': ['DELIVERED'],
        }
        allowed = driver_allowed.get(driver_status, [])
        if order.status in {'DELIVERED','REJECTED','CANCELLED','CANCELED'}:
            allowed = []
        if status == 'PICKED_UP' and restaurant_status != 'READY_FOR_PICKUP':
            raise HTTPException(409, 'Restaurant has not marked the order ready')
    else:
        allowed = RESTAURANT_TRANSITIONS.get(order.status, [])
        if status == 'DELIVERED' and order.mode != 'pickup':
            allowed = []
    if user.role == 'restaurant' and order.mode == 'pickup' and order.status == 'READY_FOR_PICKUP':
        allowed = ['DELIVERED']
    if status not in allowed:
        raise HTTPException(409, 'Invalid status transition')
    if user.role == 'restaurant' and status == 'REJECTED':
        from backend.services import cancellation_service
        from backend.schemas import CancellationInput
        estimate=cancellation_service.quote(db,order,'restaurant')
        cancellation_service.cancel(db,user,order.id,CancellationInput(reason='Restaurant declined the order',expected_status=order.status,expected_refund=estimate['refund'],expected_charge=estimate['charge']))
        return order
    requested_status = status
    if status == 'CONFIRMED':
        status = 'ACCEPTED'
    from backend.services.operations_service import notify
    notify(db, order.customer_id, 'order-status', 'Preparing Order' if status in {'ACCEPTED','PREPARING'} else status.replace('_',' ').title(), order.id)
    if status not in {'ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT'}:
        order.status = status
    db.add(DeliveryStatus(order_id=order.id, status=status))
    if status in EVENTS:
        emit(db, EVENTS[status], {'order_id':order.id})
    if requested_status == 'CONFIRMED':
        emit(db, 'ORDER_CONFIRMED', {'order_id':order.id})
    if status == 'ACCEPTED' and order.mode == 'delivery' and not order.driver_id:
        from backend.services.dispatch_service import publish
        publish(db, order)
    return order

def available(db, user):
    if not db.get(Driver, user.id).online:
        return []
    rows = db.scalars(select(Order).where(Order.driver_id == None, Order.mode == 'delivery', Order.status.in_(['ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP'])).order_by(Order.id).limit(100))
    from backend.services.dispatch_service import eligible, offer
    eligible_rows = []
    for row in rows:
        if not db.get(SystemConfig,f'driver-release:{row.id}:{user.id}') and eligible(db, user.id, row.restaurant_id):
            offer(db, row, user.id)
            eligible_rows.append(row)
    return [{
        'id': row.id,
        'restaurant_id': row.restaurant_id,
        'restaurant_name': db.get(Restaurant, row.restaurant_id).name,
        'restaurant_address': db.get(Restaurant, row.restaurant_id).address,
        'customer_name': db.get(User, row.customer_id).name,
        'address': row.address,
        'delivery_fee': row.delivery_fee,
    } for row in eligible_rows]

def accept(db, user, order_id):
    driver = db.scalar(select(Driver).where(Driver.id == user.id).with_for_update())
    if not driver.online:
        raise HTTPException(409, 'Go online first')
    active = db.scalar(select(Order.id).where(Order.driver_id == user.id, Order.status.notin_(['DELIVERED','REJECTED','CANCELLED','CANCELED'])))
    if active:
        raise HTTPException(409, 'Complete your active delivery first')
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order or order.driver_id or order.status not in ['ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP'] or order.mode != 'delivery':
        raise HTTPException(409, 'Order accepted by another driver or no longer available')
    if db.get(SystemConfig,f'driver-release:{order.id}:{user.id}'):
        raise HTTPException(409, 'You already released this delivery')
    from backend.services.dispatch_service import eligible, assigned
    if not eligible(db, user.id, order.restaurant_id):
        raise HTTPException(409, 'Share recent GPS and stay within 3 driving miles of the restaurant')
    from backend.services.operations_service import notify
    notify(db, order.customer_id, 'driver-assigned', 'Your delivery partner accepted the order.', order.id)
    order.driver_id = user.id
    assigned(db, order, user.id)
    db.add(DeliveryStatus(order_id=order.id, status='DRIVER_ASSIGNED'))
    emit(db, 'DRIVER_ASSIGNED', {'order_id':order.id, 'driver_id':user.id})
    emit(db, 'DELIVERY_ASSIGNED', {'order_id':order.id, 'driver_id':user.id})
    return order

def online(db, user, data):
    driver = db.scalar(select(Driver).where(Driver.id == user.id).with_for_update())
    driver.online = data.online
    return driver

def update_profile(db, user, data):
    driver = db.scalar(select(Driver).where(Driver.id == user.id).with_for_update())
    values = data.model_dump()
    for key, value in values.items():
        setattr(driver, key, value)
    return driver

def update_location(db, user, data):
    if data.driver_id is not None and data.driver_id != user.id:
        raise HTTPException(403, 'Driver identity does not match your session')
    driver = db.scalar(select(Driver).where(Driver.id == user.id).with_for_update())
    from backend.services.presence_service import active_delivery
    if not driver or (not driver.online and not active_delivery(db, user.id)):
        raise HTTPException(409, 'Go online before sharing location')
    if data.order_id is not None:
        requested = owned(db, user, data.order_id, True)
        if requested.mode != 'delivery' or requested.status in {'DELIVERED','REJECTED','CANCELLED','CANCELED'}:
            raise HTTPException(409, 'Delivery is no longer active')
    row = db.scalar(select(DriverLocation).where(DriverLocation.driver_id == user.id).with_for_update())
    if not row:
        row = DriverLocation(driver_id=user.id, latitude=data.latitude, longitude=data.longitude, heading=data.heading)
        db.add(row)
    else:
        row.latitude = data.latitude
        row.longitude = data.longitude
        row.heading = data.heading
        row.updated_at = now()
    active_order = db.scalar(select(Order.id).where(Order.driver_id == user.id, Order.status.notin_(['DELIVERED','REJECTED','CANCELLED','CANCELED'])).order_by(Order.id.desc()))
    if active_order:
        arrival_order = db.scalar(select(Order).where(Order.id == active_order).with_for_update())
        if arrival_order and arrival_order.driver_id == user.id:
            from backend.services.arrival_service import detect
            detect(db, arrival_order, row.latitude, row.longitude)
    emit(db, 'DRIVER_LOCATION_UPDATED', {'driver_id': user.id, 'order_id': active_order, 'latitude': data.latitude, 'longitude': data.longitude})
    return {'driver_id': user.id, 'order_id': active_order, 'latitude': row.latitude, 'longitude': row.longitude, 'heading': row.heading, 'updated_at': row.updated_at}

def location_for_order(db, user, order_id):
    order = owned(db, user, order_id)
    if not order.driver_id or order.status in {'DELIVERED','REJECTED','CANCELLED','CANCELED'}:
        return None
    row = db.get(DriverLocation, order.driver_id)
    if not row:
        return None
    driver_user = db.get(User, order.driver_id)
    driver = db.get(Driver, order.driver_id)
    return {
        'order_id': order.id,
        'driver': {'id': order.driver_id, 'name': driver_user.name, 'phone': driver_user.phone, 'vehicle_type': driver.vehicle_type, 'vehicle_number': driver.vehicle_number},
        'latitude': row.latitude,
        'longitude': row.longitude,
        'heading': row.heading,
        'updated_at': row.updated_at,
    }

def stats(db, user, period):
    days = {'daily':1,'weekly':7,'monthly':30}.get(period)
    if not days:
        raise HTTPException(400, 'Invalid period')
    field = Order.restaurant_id if user.role == 'restaurant' else Order.driver_id
    filters = [field == user.id, Order.status == 'DELIVERED', Order.created_at >= now()-timedelta(days=days)]
    amount = Order.total-Order.delivery_fee-func.coalesce(Order.tip,0) if user.role == 'restaurant' else Order.delivery_fee+func.coalesce(Order.tip,0)
    count, revenue = db.execute(select(func.count(Order.id), func.coalesce(func.sum(amount),0)).where(*filters)).one()
    top = []
    if user.role == 'restaurant':
        rows = db.execute(select(OrderItem.name, func.sum(OrderItem.quantity).label('units')).join(Order, OrderItem.order_id == Order.id).where(*filters).group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(10))
        top = [{'name':name, 'units':units} for name,units in rows]
    return {'period':period, 'orders':count, 'revenue':revenue, 'top_items':top}


def payment_history(db, user):
    orders = list(db.scalars(select(Order).where(Order.driver_id == user.id).order_by(Order.id.desc()).limit(500)))
    paid = {}
    if orders:
        for row in db.scalars(select(PayoutTransaction).where(PayoutTransaction.payee_role == 'driver', PayoutTransaction.order_id.in_([order.id for order in orders]))):
            paid[row.order_id] = paid.get(row.order_id, Decimal('0')) + Decimal(str(row.amount or 0))
    rows = []
    total_earned = Decimal('0')
    total_paid = Decimal('0')
    for order in orders:
        amount = Decimal(str(order.delivery_fee or 0)) + Decimal(str(order.tip or 0)) if order.mode == 'delivery' else Decimal('0')
        paid_amount = paid.get(order.id, Decimal('0'))
        total_earned += amount if order.status == 'DELIVERED' else Decimal('0')
        total_paid += paid_amount
        status = 'PAID' if paid_amount >= amount and amount > 0 else ('PENDING ADMIN PAY' if order.status == 'DELIVERED' and amount > 0 else 'NOT READY')
        restaurant = db.get(Restaurant, order.restaurant_id)
        customer = db.get(User, order.customer_id)
        rows.append({
            'order_id': order.id,
            'restaurant_name': restaurant.name if restaurant else 'Restaurant',
            'customer_name': customer.name if customer else 'Customer',
            'order_status': order.status,
            'payment_status': status,
            'payment_mode': order.payment_mode or 'Card',
            'delivery_fee': order.delivery_fee,
            'tip': order.tip,
            'payout_amount': amount,
            'paid_amount': paid_amount,
            'pending_amount': max(amount - paid_amount, Decimal('0')),
            'timestamp': order.created_at,
        })
    return {'rows': rows, 'summary': {'earned': total_earned, 'paid': total_paid, 'pending': max(total_earned - total_paid, Decimal('0'))}}
