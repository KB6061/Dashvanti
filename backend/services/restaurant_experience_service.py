import math
import secrets
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from backend.models import Restaurant, RestaurantPresentation, MenuItem, Rating, Review, Order, OrderItem, User, File, Customer, CustomerLocation, CartItem, DeliveryStatus
from backend.restaurant_experience_models import RestaurantPlan, ScheduledOrder, GroupOrder, GroupMember, GroupItem
from backend.services import restaurant_service, order_service

def store(db, restaurant_id):
    row = db.get(Restaurant, restaurant_id)
    if not row:
        raise HTTPException(404, 'Restaurant not found')
    return row

def store_zone(row):
    from timezonefinder import TimezoneFinder
    global _zones
    if '_zones' not in globals():
        _zones = TimezoneFinder(in_memory=False)
    name = _zones.timezone_at(lat=row.latitude, lng=row.longitude) if row.latitude is not None and row.longitude is not None else None
    return ZoneInfo(name or 'UTC')

def slots(row):
    zone = store_zone(row)
    now = datetime.now(zone)
    result = []
    for day in range(7):
        start = datetime.combine((now + timedelta(days=day)).date(), datetime.strptime(row.opening, '%H:%M').time(), zone)
        end = datetime.combine(start.date(), datetime.strptime(row.closing, '%H:%M').time(), zone)
        if end <= start:
            end += timedelta(days=1)
        while start < end:
            if start >= now + timedelta(minutes=30):
                result.append({'value': start.astimezone(timezone.utc).isoformat(), 'label': start.strftime('%a %b %d, %I:%M %p')})
            start += timedelta(minutes=30)
    return result

def set_plan(db, user, restaurant_id, value):
    row = store(db, restaurant_id)
    if value is not None and value not in {slot['value'] for slot in slots(row)}:
        raise HTTPException(422, 'Choose an available preparation time')
    plan = db.get(RestaurantPlan, (user.id, restaurant_id))
    if plan is None:
        plan = RestaurantPlan(customer_id=user.id, restaurant_id=restaurant_id)
        db.add(plan)
    plan.scheduled_for = datetime.fromisoformat(value).astimezone(timezone.utc).replace(tzinfo=None) if value else None
    db.flush()
    return {'scheduled_for': value}

def selected_time(db, user, restaurant_id):
    plan = db.get(RestaurantPlan, (user.id, restaurant_id))
    if not plan or not plan.scheduled_for:
        return None
    if plan.scheduled_for <= datetime.utcnow() + timedelta(minutes=1):
        raise HTTPException(409, 'Scheduled time expired. Choose another time or ASAP.')
    return plan.scheduled_for

def experience(db, restaurant_id, user=None):
    row = store(db, restaurant_id)
    menu = list(db.scalars(select(MenuItem).where(MenuItem.restaurant_id == row.id, MenuItem.available == True).order_by(MenuItem.id)))
    menu_photos = {}
    if menu:
        for photo in db.scalars(select(File).where(File.purpose == 'menu', File.entity_id.in_([item.id for item in menu])).order_by(File.id.desc())):
            bucket = menu_photos.setdefault(photo.entity_id, [])
            if len(bucket) < 5:
                bucket.append(f'/api/files/{photo.id}/thumbnail')
    profile_photos = list(db.scalars(select(File.id).where(File.user_id == row.id, File.purpose == 'profile').order_by(File.id.desc()).limit(5)))
    presentation = db.get(RestaurantPresentation, row.id)
    owner = db.get(User, row.id)
    result = {'restaurant': row, 'phone': owner.phone if owner else '', 'opening_label': restaurant_service._clock_label(row.opening), 'closing_label': restaurant_service._clock_label(row.closing),
              'photo_urls': [f'/api/files/{file_id}' for file_id in profile_photos],
              'presentation': {'cover_file_id': presentation.cover_file_id, 'logo_file_id': presentation.logo_file_id, 'gallery_file_ids': json.loads(presentation.gallery_file_ids or '[]')} if presentation else {},
              'price_range': {'min': min((item.price for item in menu), default=0), 'max': max((item.price for item in menu), default=0)},
              'menu': [{'id': item.id, 'name': item.name, 'description': item.description, 'price': item.price, 'category': item.category or 'General', 'veg': item.veg, 'available': item.available, 'photo_urls': menu_photos.get(item.id, [])} for item in menu]}
    customer = db.get(Customer, user.id) if user and user.role == 'customer' else None
    location = db.get(CustomerLocation, user.id) if customer else None
    distance = None
    if location and all(x is not None for x in (location.latitude, location.longitude, row.latitude, row.longitude)):
        a, b = math.radians(location.latitude), math.radians(row.latitude)
        h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(row.longitude-location.longitude)/2)**2
        distance = round(3958.7613 * 2 * math.asin(min(1, math.sqrt(h))), 2)
    result['distance_miles'] = distance
    result['distance_type'] = 'straight_line'
    if distance is not None:
        from backend.services.eta_service import route
        road = route((location.latitude, location.longitude), (row.latitude, row.longitude))
        if road.get('distance_type') == 'driving':
            result['distance_miles'] = road['distance_miles']
            result['distance_type'] = 'driving'
    count, average = db.execute(select(func.count(Rating.id), func.avg(Rating.restaurant)).join(Order, Rating.order_id == Order.id).where(Order.restaurant_id == row.id)).one()
    result['rating_count'] = count or 0
    result['rating'] = round(float(average or 0), 1)
    reviews = db.execute(select(Review, Rating.restaurant, User.name).join(Order, Review.order_id == Order.id).join(User, Review.customer_id == User.id).outerjoin(Rating, Rating.order_id == Order.id).where(Order.restaurant_id == row.id).order_by(Review.id.desc()).limit(100)).all()
    review_photos = {}
    if reviews:
        for photo in db.scalars(select(File).where(File.purpose == 'review', File.entity_id.in_([review.id for review, _, _ in reviews])).order_by(File.id)):
            bucket = review_photos.setdefault(photo.entity_id, [])
            if len(bucket) < 5:
                bucket.append(f'/api/files/{photo.id}/thumbnail')
    result['reviews'] = [{'id': review.id, 'text': review.text, 'rating': rating, 'name': name, 'photo_urls': review_photos.get(review.id, [])} for review, rating, name in reviews]
    result['customer_photos'] = [photo for review in result['reviews'] for photo in review['photo_urls']]
    result['customer_photo_count'] = db.scalar(select(func.count(File.id)).join(Review, File.entity_id == Review.id).join(Order, Review.order_id == Order.id).where(File.purpose == 'review', Order.restaurant_id == row.id)) or 0
    result['popular_ids'] = list(db.scalars(select(OrderItem.menu_item_id).join(Order, OrderItem.order_id == Order.id).where(Order.restaurant_id == row.id, Order.status == 'DELIVERED').group_by(OrderItem.menu_item_id).order_by(func.sum(OrderItem.quantity).desc()).limit(12)))
    result['timezone'] = str(store_zone(row))
    result['schedule_slots'] = slots(row)
    result['eligible_order_ids'] = list(db.scalars(select(Order.id).where(Order.customer_id == user.id, Order.restaurant_id == row.id, Order.status == 'DELIVERED', ~Order.id.in_(select(Review.order_id))).order_by(Order.id.desc()).limit(20))) if customer else []
    plan = db.get(RestaurantPlan, (user.id, restaurant_id)) if customer else None
    result['scheduled_for'] = plan.scheduled_for.replace(tzinfo=timezone.utc).isoformat() if plan and plan.scheduled_for else None
    result['order_mode'] = customer.order_mode if customer else 'delivery'
    from backend.services.fund_service import calculate
    result['fee_example'] = calculate(db, Decimal('0'), 'delivery')
    result['fee_example_label'] = 'Base fees; checkout shows the final tax, fees and total.'
    active = db.scalar(select(GroupOrder).join(GroupMember, GroupMember.group_id == GroupOrder.id).where(GroupMember.customer_id == user.id, GroupOrder.restaurant_id == row.id, GroupOrder.status == 'OPEN', GroupOrder.expires_at > datetime.utcnow()).order_by(GroupOrder.expires_at.desc()).limit(1)) if customer else None
    result['active_group'] = group_data(db, user, active.id) if active else None
    return result

def customer_photos(db, restaurant_id, page=1):
    store(db, restaurant_id)
    query = select(File.id).join(Review, File.entity_id == Review.id).join(Order, Review.order_id == Order.id).where(File.purpose == 'review', Order.restaurant_id == restaurant_id)
    ids = list(db.scalars(query.order_by(File.id.desc()).offset((page-1)*24).limit(25)))
    return {'items': [f'/api/files/{file_id}' for file_id in ids[:24]], 'has_more': len(ids) > 24}

def group(db, user, group_id, lock=False):
    query = select(GroupOrder).where(GroupOrder.id == group_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if not row or not db.get(GroupMember, (group_id, user.id)):
        raise HTTPException(404, 'Group order not found')
    if row.expires_at <= datetime.utcnow():
        raise HTTPException(410, 'Group invitation expired')
    return row

def group_data(db, user, group_id):
    row = group(db, user, group_id)
    items = db.execute(select(GroupItem, MenuItem.name, MenuItem.price, User.name).join(MenuItem, GroupItem.menu_item_id == MenuItem.id).join(User, GroupItem.customer_id == User.id).where(GroupItem.group_id == group_id)).all()
    return {'id': row.id, 'restaurant_id': row.restaurant_id, 'restaurant_name': store(db, row.restaurant_id).name, 'invite_code': row.invite_code, 'host': row.host_id == user.id, 'status': row.status,
            'members': list(db.scalars(select(User.name).join(GroupMember, GroupMember.customer_id == User.id).where(GroupMember.group_id == row.id))),
            'items': [{'menu_item_id': item.menu_item_id, 'customer_id': item.customer_id, 'quantity': item.quantity, 'name': name, 'price': price, 'member': member, 'mine': item.customer_id == user.id} for item, name, price, member in items]}

def create_group(db, user, restaurant_id):
    store(db, restaurant_id)
    order_service.customer_lock(db, user)
    existing = db.scalar(select(GroupOrder).join(GroupMember, GroupMember.group_id == GroupOrder.id).where(
        GroupMember.customer_id == user.id, GroupOrder.restaurant_id == restaurant_id,
        GroupOrder.status == 'OPEN', GroupOrder.expires_at > datetime.utcnow()).limit(1))
    if existing:
        return group_data(db, user, existing.id)
    row = GroupOrder(id=secrets.token_hex(16), invite_code=secrets.token_hex(12), restaurant_id=restaurant_id, host_id=user.id, expires_at=datetime.utcnow()+timedelta(hours=24))
    db.add(row); db.flush()
    db.add(GroupMember(group_id=row.id, customer_id=user.id)); db.flush()
    return group_data(db, user, row.id)

def join_group(db, user, code):
    row = db.scalar(select(GroupOrder).where(GroupOrder.invite_code == code.strip().lower()).with_for_update())
    if not row or row.expires_at <= datetime.utcnow() or row.status != 'OPEN':
        raise HTTPException(404, 'Invitation expired or group is closed')
    if not db.get(GroupMember, (row.id, user.id)):
        count = db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == row.id))
        if count >= 20:
            raise HTTPException(409, 'Group is full')
        db.add(GroupMember(group_id=row.id, customer_id=user.id)); db.flush()
    return group_data(db, user, row.id)

def change_group(db, user, group_id, item_id, quantity):
    row = group(db, user, group_id, True)
    if row.status != 'OPEN':
        raise HTTPException(409, 'Host has locked the group')
    item = db.get(MenuItem, item_id)
    if not item or item.restaurant_id != row.restaurant_id or not item.available:
        raise HTTPException(404, 'Menu item unavailable')
    existing = db.get(GroupItem, (group_id, user.id, item_id))
    if existing:
        if quantity:
            existing.quantity = quantity
        else:
            db.delete(existing)
    elif quantity:
        db.add(GroupItem(group_id=group_id, customer_id=user.id, menu_item_id=item_id, quantity=quantity))
    db.flush()
    return group_data(db, user, group_id)

def remove_group(db, user, group_id):
    row = group(db, user, group_id, True)
    if row.status != 'OPEN':
        raise HTTPException(409, 'This group has already checked out')
    if row.host_id == user.id:
        db.execute(delete(GroupItem).where(GroupItem.group_id == row.id))
        db.execute(delete(GroupMember).where(GroupMember.group_id == row.id))
        db.delete(row)
    else:
        db.execute(delete(GroupItem).where(GroupItem.group_id == row.id, GroupItem.customer_id == user.id))
        db.execute(delete(GroupMember).where(GroupMember.group_id == row.id, GroupMember.customer_id == user.id))
    db.flush()
    return {'removed': True}

def finish_group(db, user, group_id):
    order_service.customer_lock(db, user)
    row = group(db, user, group_id, True)
    if row.host_id != user.id:
        raise HTTPException(403, 'Only the host can check out')
    if row.status == 'LOCKED':
        return order_service.cart(db, user)
    items = db.execute(select(GroupItem.menu_item_id, func.sum(GroupItem.quantity)).where(GroupItem.group_id == group_id).group_by(GroupItem.menu_item_id)).all()
    if not items:
        raise HTTPException(409, 'Add items before checkout')
    if db.scalar(select(CartItem.id).where(CartItem.customer_id == user.id).limit(1)):
        raise HTTPException(409, 'Complete or clear your personal cart before group checkout')
    for item_id, quantity in items:
        item = db.get(MenuItem, item_id)
        if not item or not item.available or quantity > 50:
            raise HTTPException(409, 'Some items are unavailable or exceed the quantity limit')
        db.add(CartItem(customer_id=user.id, menu_item_id=item_id, quantity=quantity))
    row.status = 'LOCKED'; db.flush()
    return order_service.cart(db, user)

def release_due(db, order_ids=None):
    query = select(ScheduledOrder).where(ScheduledOrder.released == False, ScheduledOrder.release_at <= datetime.utcnow())
    if order_ids is not None:
        query = query.where(ScheduledOrder.order_id.in_(order_ids))
    rows = list(db.scalars(query.with_for_update(skip_locked=True).limit(100)))
    from backend.services.kafka_event_service import emit
    for schedule in rows:
        order = db.scalar(select(Order).where(Order.id == schedule.order_id).with_for_update())
        if order and order.status == 'SCHEDULED':
            restaurant = db.get(Restaurant, order.restaurant_id)
            from backend.services.store_status_service import accepting
            if not accepting(db, restaurant):
                if datetime.utcnow() >= schedule.release_at + timedelta(minutes=15):
                    order.status = 'REJECTED'
                    db.add(DeliveryStatus(order_id=order.id, status='REJECTED'))
                    from backend.services.operations_service import notify
                    notify(db, order.customer_id, 'scheduled-order-unavailable', 'The restaurant is unavailable for your scheduled order. No cash payment is due.', order.id)
                    schedule.released = True
                continue
            order.status = 'PLACED'
            db.add(DeliveryStatus(order_id=order.id, status='PLACED'))
            emit(db, 'ORDER_CREATED', {'order_id': order.id, 'restaurant_id': order.restaurant_id})
            from backend.services.restaurant_auto_accept_service import accept_order
            accept_order(db, order)
        schedule.released = True
    db.flush()

if __name__ == '__main__':
    from backend.db import Session
    from backend.services.order_broadcast_service import install
    install()
    with Session() as db:
        release_due(db); db.commit()
