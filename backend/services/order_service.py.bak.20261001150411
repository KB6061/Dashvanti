import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from backend.models import User, CartItem, MenuItem, Restaurant, Driver, Address, Order, OrderItem, DeliveryStatus, Rating, Review, Promotion, RestaurantPresentation
from backend.services.kafka_event_service import emit
from backend.services.fund_service import calculate

TAX_RATE = Decimal('0.00')
DISCOUNT = Decimal('0.00')
DELIVERY_FEE = Decimal('30.00')
RESTAURANT_ORDER_LOG = Path(os.environ.get('RESTAURANT_ORDER_LOG','/home/krishna/food/logs/restaurant-orders.log'))

def log_restaurant_order(order, customer, restaurant, rows, address):
    try:
        RESTAURANT_ORDER_LOG.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'timestamp': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            'event': 'ORDER_NOTIFICATION_CREATED',
            'order_id': order.id,
            'status': order.status,
            'mode': order.mode,
            'restaurant': {'id': restaurant.id, 'name': restaurant.name},
            'customer': {'id': customer.id, 'name': customer.name, 'email': customer.email, 'phone': customer.phone},
            'address': address,
            'total': str(order.total),
            'delivery_fee': str(order.delivery_fee),
            'items': [{'name': m.name, 'quantity': c.quantity,
            'special_instructions': c.special_instructions, 'price': str(m.price), 'subtotal': str(m.price * c.quantity)} for c,m in rows],
        }
        with RESTAURANT_ORDER_LOG.open('a', encoding='utf-8') as log_file:
            log_file.write(json.dumps(payload, sort_keys=True) + '\n')
    except OSError:
        pass

def customer_lock(db, user):
    db.scalar(select(User).where(User.id == user.id).with_for_update())

def totals(subtotal, mode='delivery', discount=Decimal('0.00')):
    tax = (subtotal * TAX_RATE).quantize(Decimal('0.01'))
    delivery_fee = DELIVERY_FEE if mode == 'delivery' else Decimal('0.00')
    discount = min(discount or DISCOUNT, subtotal + tax)
    total = subtotal + tax + delivery_fee - discount
    return {'subtotal': subtotal, 'tax': tax, 'delivery_fee': delivery_fee, 'discount': discount, 'total': total}


def promotion_discount(db, user, code, subtotal, has_prior_order=None):
    if not code:
        return Decimal('0.00')
    now = datetime.utcnow()
    row = db.scalar(select(Promotion).where(func.upper(Promotion.code) == code.upper(), Promotion.enabled == True))
    if not row or (row.starts_at and row.starts_at > now) or (row.ends_at and row.ends_at < now):
        raise HTTPException(409, 'Promotion is not available')
    if subtotal < row.minimum:
        raise HTTPException(409, 'Order does not meet the promotion minimum')
    if row.first_order_only and (has_prior_order if has_prior_order is not None else db.scalar(select(Order.id).where(Order.customer_id == user.id).limit(1))):
        raise HTTPException(409, 'Promotion is for a first order only')
    value = (subtotal * Decimal(row.percent) / Decimal('100')).quantize(Decimal('0.01'))
    return min(value, row.cap) if row.cap else value

def cart(db, user):
    rows = db.execute(select(CartItem, MenuItem).join(MenuItem, CartItem.menu_item_id == MenuItem.id).where(CartItem.customer_id == user.id)).all()
    subtotal = sum((m.price*c.quantity for c,m in rows), Decimal('0.00'))
    items = []
    groups = {}
    for c,m in rows:
        restaurant = db.get(Restaurant, m.restaurant_id)
        item = {
            'menu_item_id': m.id,
            'restaurant_id': m.restaurant_id,
            'restaurant_name': restaurant.name if restaurant else '',
            'restaurant_address': restaurant.address if restaurant else '',
            'name': m.name,
            'price': m.price,
            'quantity': c.quantity,
            'special_instructions': c.special_instructions,
            'subtotal': m.price * c.quantity,
            'veg': m.veg,
        }
        items.append(item)
        group = groups.setdefault(m.restaurant_id, {
            'restaurant_id': m.restaurant_id,
            'restaurant_name': item['restaurant_name'],
            'restaurant_address': item['restaurant_address'],
            'delivery_minutes': restaurant.delivery_minutes if restaurant else 30,
            'items': [],
            'item_count': 0,
            'subtotal': Decimal('0.00'),
        })
        group['items'].append(item)
        group['item_count'] += c.quantity
        group['subtotal'] += item['subtotal']
    return {'items': items, 'groups': list(groups.values()), **calculate(db, subtotal, 'pickup')}


def checkout_quote(db, user, data):
    cart_data = cart(db, user)
    has_prior_order = bool(db.scalar(
        select(Order.id).where(Order.customer_id == user.id).limit(1)
    ))
    groups = []
    subtotal = Decimal('0.00')
    tax = Decimal('0.00')
    service_fee = Decimal('0.00')
    delivery_fee = Decimal('0.00')
    discount = Decimal('0.00')
    total = Decimal('0.00')
    tips = allocate_tip(data.tip if data.mode == 'delivery' else Decimal('0'), [g['restaurant_id'] for g in cart_data['groups']])
    for group in cart_data['groups']:
        group_discount = promotion_discount(
            db,
            user,
            data.promo_code,
            group['subtotal'],
            has_prior_order,
        )
        calculated = calculate(db, group['subtotal'], data.mode, group_discount)
        calculated['tip'] = tips[group['restaurant_id']]
        calculated['total'] += calculated['tip']
        groups.append({
            'restaurant_id': group['restaurant_id'],
            'restaurant_name': group['restaurant_name'],
            'restaurant_address': group['restaurant_address'],
            'item_count': group['item_count'],
            **calculated,
        })
        subtotal += calculated['subtotal']
        tax += calculated['tax']
        service_fee += calculated['service_fee']
        delivery_fee += calculated['delivery_fee']
        discount += calculated['discount']
        total += calculated['total']
    return {
        'mode': data.mode,
        'tip': sum(tips.values(), Decimal('0')),
        'groups': groups,
        'subtotal': subtotal,
        'tax': tax,
        'service_fee': service_fee,
        'delivery_fee': delivery_fee,
        'discount': discount,
        'total': total,
    }

def update_cart(db, user, data):
    customer_lock(db, user)
    item = db.get(MenuItem, data.menu_item_id)
    if not item or not item.available:
        raise HTTPException(404, 'Menu item unavailable')
    if data.quantity:
        from backend.services.store_status_service import accepting
        if not accepting(db, db.get(Restaurant, item.restaurant_id)):
            raise HTTPException(409, 'This store is currently closed')
    rows = list(db.scalars(select(CartItem).where(CartItem.customer_id == user.id)))
    existing = next((r for r in rows if r.menu_item_id == item.id), None)
    if existing:
        if data.quantity:
            existing.quantity = data.quantity
            if data.special_instructions is not None:
                existing.special_instructions = data.special_instructions
        else:
            db.delete(existing)
    elif data.quantity:
        db.add(CartItem(customer_id=user.id, menu_item_id=item.id, quantity=data.quantity, special_instructions=data.special_instructions))
    db.flush()
    return cart(db, user)

def checkout(db, user, data):
    customer_lock(db, user)
    base_key = data.request_key[:48]
    prior = db.scalar(select(Order).where(Order.customer_id == user.id, Order.request_key.like(base_key + ':%')).order_by(Order.id))
    if prior:
        order_ids = list(db.scalars(select(Order.id).where(Order.customer_id == user.id, Order.request_key.like(base_key + ':%')).order_by(Order.id)))
        return {'id': prior.id, 'order_ids': order_ids, 'message': f'{len(order_ids)} order placed'}
    rows = db.execute(select(CartItem, MenuItem).join(MenuItem, CartItem.menu_item_id == MenuItem.id).where(CartItem.customer_id == user.id)).all()
    if not rows:
        raise HTTPException(400, 'Cart is empty')
    address = 'Pickup at restaurant'
    if data.mode == 'delivery':
        row = db.get(Address, data.address_id) if data.address_id else None
        if not row or row.customer_id != user.id:
            raise HTTPException(400, 'Choose a delivery address')
        address = row.details
    grouped = {}
    for c,m in rows:
        restaurant = db.get(Restaurant, m.restaurant_id)
        if not restaurant or not restaurant.is_open or not m.available:
            raise HTTPException(409, 'Restaurant or items unavailable')
        presentation = db.get(RestaurantPresentation, restaurant.id)
        if presentation and presentation.busy_mode == 'paused':
            raise HTTPException(409, 'Restaurant is not accepting new orders')
        if presentation:
            active_orders = db.scalar(select(func.count(Order.id)).where(
                Order.restaurant_id == restaurant.id,
                Order.status.in_(['PLACED', 'CONFIRMED', 'ACCEPTED', 'PREPARING']),
            )) or 0
            if active_orders >= presentation.capacity:
                raise HTTPException(409, 'Restaurant has reached its order capacity')
        grouped.setdefault(m.restaurant_id, {'restaurant': restaurant, 'rows': []})['rows'].append((c,m))
    has_prior_order = bool(db.scalar(select(Order.id).where(Order.customer_id == user.id).limit(1)))
    orders = []
    tips = allocate_tip(data.tip if data.mode == 'delivery' else Decimal('0'), grouped)
    for restaurant_id, group in grouped.items():
        subtotal = sum((m.price*c.quantity for c,m in group['rows']), Decimal('0.00'))
        discount = promotion_discount(db, user, data.promo_code, subtotal, has_prior_order)
        calculated = calculate(db, subtotal, data.mode, discount)
        calculated['total'] += tips[restaurant_id]
        order = Order(tip=tips[restaurant_id], customer_id=user.id, restaurant_id=restaurant_id, request_key=f'{base_key}:{restaurant_id}', mode=data.mode, address=address, total=calculated['total'], tax=calculated['tax'], service_fee=calculated['service_fee'], delivery_fee=calculated['delivery_fee'], discount=calculated['discount'])
        db.add(order)
        db.flush()
        from backend.services.cancellation_service import snapshot
        snapshot(db, order)
        for c,m in group['rows']:
            db.add(OrderItem(order_id=order.id, menu_item_id=m.id, name=m.name, quantity=c.quantity, price=m.price, special_instructions=c.special_instructions))
        db.add(DeliveryStatus(order_id=order.id, status='PLACED'))
        emit(db, 'ORDER_CREATED', {'order_id': order.id, 'restaurant_id': restaurant_id})
        log_restaurant_order(order, user, group['restaurant'], group['rows'], address)
        orders.append(order)
    for c,m in rows:
        db.delete(c)
    total = sum((order.total for order in orders), Decimal('0.00'))
    discount = sum((order.discount or Decimal('0.00') for order in orders), Decimal('0.00'))
    delivery_fee = sum((order.delivery_fee for order in orders), Decimal('0.00'))
    return {'id': orders[0].id, 'order_ids': [order.id for order in orders], 'total': total, 'discount': discount, 'delivery_fee': delivery_fee, 'message': f'{len(orders)} order placed'}

def owned(db, user, order_id, lock=False):
    stmt = select(Order).where(Order.id == order_id)
    if lock:
        stmt = stmt.with_for_update()
    order = db.scalar(stmt)
    field = {'customer':'customer_id','restaurant':'restaurant_id','driver':'driver_id'}[user.role]
    if not order or getattr(order, field) != user.id:
        raise HTTPException(404, 'Order not found')
    return order

def listing(db, user):
    field = getattr(Order, {'customer':'customer_id','restaurant':'restaurant_id','driver':'driver_id'}[user.role])
    query = select(Order).where(field == user.id).order_by(Order.id.desc())
    rows = list(db.scalars(query if user.role in {'customer', 'restaurant'} else query.limit(200)))
    order_items = {}
    for item in db.scalars(select(OrderItem).join(Order, Order.id == OrderItem.order_id).where(field == user.id)):
        order_items.setdefault(item.order_id, []).append({'name': item.name, 'quantity': item.quantity, 'price': item.price})

    result = []
    for order in rows:
        restaurant = db.get(Restaurant, order.restaurant_id)
        customer = db.get(User, order.customer_id)
        driver = db.get(User, order.driver_id) if order.driver_id else None
        result.append({
            'items': order_items.get(order.id, []),
            'item_count': sum(item['quantity'] for item in order_items.get(order.id, [])),
            'id': order.id,
            'status': order.status,
            'mode': order.mode,
            'address': order.address,
            'total': order.total,
            'tip': order.tip,
            'delivery_fee': order.delivery_fee,
            'discount': order.discount,
            'created_at': order.created_at,
            'restaurant_name': restaurant.name if restaurant else '',
            'restaurant_address': restaurant.address if restaurant else '',
            'customer_name': customer.name if customer else '',
            'customer_email': customer.email if customer else '',
            'customer_phone': customer.phone if customer else '',
            'driver_name': driver.name if driver else '',
        })
    return result

def detail(db, user, order_id):
    order = owned(db, user, order_id)
    driver = db.get(User, order.driver_id) if order.driver_id else None
    driver_profile = db.get(Driver, order.driver_id) if order.driver_id else None
    customer = db.get(User, order.customer_id)
    restaurant = db.get(Restaurant, order.restaurant_id)
    return {
        'restaurant': {'name': restaurant.name, 'address': restaurant.address},
        'customer': {'name': customer.name, 'phone': customer.phone} if customer else None,
        'order': order,
        'items': list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id))),
        'history': list(db.scalars(select(DeliveryStatus).where(DeliveryStatus.order_id == order.id).order_by(DeliveryStatus.id))),
        'driver': {'name':driver.name, 'phone':driver.phone, 'vehicle_type': driver_profile.vehicle_type if driver_profile else '', 'vehicle_number': driver_profile.vehicle_number if driver_profile else ''} if driver else None
    }

def reorder(db, user, order_id):
    customer_lock(db, user)
    order = owned(db, user, order_id)
    items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
    if any(not db.get(MenuItem, item.menu_item_id).available for item in items):
        raise HTTPException(409, 'Some items are no longer available')
    db.execute(delete(CartItem).where(CartItem.customer_id == user.id))
    for item in items:
        db.add(CartItem(customer_id=user.id, menu_item_id=item.menu_item_id, quantity=item.quantity, special_instructions=item.special_instructions))
    db.flush()
    return cart(db, user)

def review(db, user, order_id, data):
    order = owned(db, user, order_id, True)
    if order.status != 'DELIVERED':
        raise HTTPException(409, 'Review a completed order')
    if db.scalar(select(Review).where(Review.order_id == order.id)):
        raise HTTPException(409, 'Order already reviewed')
    if data.driver and not order.driver_id:
        raise HTTPException(400, 'This order has no driver')
    db.add(Rating(order_id=order.id, restaurant=data.restaurant, driver=data.driver))
    row = Review(order_id=order.id, customer_id=user.id, text=data.text)
    db.add(row)
    db.flush()
    emit(db, 'REVIEW_POSTED', {'order_id': order.id, 'review_id': row.id})
    return row

def allocate_tip(tip, restaurant_ids):
    ids = sorted(restaurant_ids)
    if not ids:
        return {}
    cents, remainder = divmod(int(tip * 100), len(ids))
    return {key: Decimal(cents + (index < remainder)) / 100 for index, key in enumerate(ids)}
