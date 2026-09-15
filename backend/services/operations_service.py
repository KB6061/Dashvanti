import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from backend.models import (
    Address, AuditEvent, CartItem, Customer, CustomerLocation, DeliveryStatus,
    Driver, DriverLocation, File, MenuItem, Notification, Order, OrderItem,
    OrderMessage, PasswordReset, PlatformContent, Promotion, Rating, Restaurant,
    RestaurantPresentation, Review, SupportTicket, User,
)
from backend.services import order_service

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def audit(db, actor_id, action, target, details='-'):
    db.add(AuditEvent(actor_id=actor_id, action=action, target=target, details=details or '-'))

def notify(db, user_id, kind, body, order_id=None):
    if user_id:
        db.add(Notification(user_id=user_id, order_id=order_id, kind=kind, body=body))

def _file(db, user, file_id):
    if file_id is None:
        return None
    row = db.get(File, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, 'Media file not found')
    if row.purpose not in {'cover', 'logo', 'gallery'}:
        raise HTTPException(400, 'Unsupported media file')
    return row

def presentation(db, user):
    row = db.get(RestaurantPresentation, user.id)
    if not row:
        return {
            'cover_file_id': None, 'logo_file_id': None, 'gallery_file_ids': [],
            'busy_mode': 'open', 'busy_until': None, 'prep_extra_minutes': 0, 'capacity': 20,
        }
    return {
        'cover_file_id': row.cover_file_id, 'logo_file_id': row.logo_file_id,
        'gallery_file_ids': json.loads(row.gallery_file_ids or '[]'),
        'busy_mode': row.busy_mode, 'busy_until': row.busy_until,
        'prep_extra_minutes': row.prep_extra_minutes, 'capacity': row.capacity,
    }

def save_presentation(db, user, data):
    payload = data.model_dump()
    gallery = list(dict.fromkeys(payload.pop('gallery_file_ids')))
    if len(gallery) > 12:
        raise HTTPException(422, 'Use up to 12 gallery photos')
    for file_id in [payload['cover_file_id'], payload['logo_file_id'], *gallery]:
        _file(db, user, file_id)
    values = {
        'cover_file_id': payload['cover_file_id'],
        'logo_file_id': payload['logo_file_id'],
        'gallery_file_ids': json.dumps(gallery),
        'busy_mode': payload['busy_mode'],
        'busy_until': payload['busy_until'],
        'prep_extra_minutes': payload['prep_extra_minutes'],
        'capacity': payload['capacity'],
        'updated_at': utcnow(),
    }
    updated = db.execute(update(RestaurantPresentation).where(RestaurantPresentation.restaurant_id == user.id).values(**values)).rowcount
    if not updated:
        db.add(RestaurantPresentation(restaurant_id=user.id, **values))
    audit(db, user.id, 'restaurant-presentation-saved', f'restaurant:{user.id}')
    db.flush()
    return presentation(db, user)

def home(db):
    banner = db.get(PlatformContent, 'home_banner')
    now = utcnow()
    rows = list(db.scalars(select(Promotion).where(Promotion.enabled == True).order_by(Promotion.id.desc())))
    deals = [
        {
            'id': row.id, 'title': row.title, 'description': row.description, 'code': row.code,
            'percent': row.percent, 'minimum': row.minimum, 'cap': row.cap,
            'first_order_only': row.first_order_only, 'starts_at': row.starts_at, 'ends_at': row.ends_at,
        }
        for row in rows
        if (not row.starts_at or row.starts_at <= now) and (not row.ends_at or row.ends_at >= now)
    ]
    return {
        'banner': {
            'title': banner.title if banner else '', 'description': banner.description if banner else '',
            'enabled': bool(banner and banner.enabled), 'media_file_id': banner.media_file_id if banner else None,
        },
        'promotions': deals,
    }

def save_banner(db, data):
    row = db.get(PlatformContent, 'home_banner')
    if not row:
        row = PlatformContent(key='home_banner')
        db.add(row)
    row.title = data.title
    row.description = data.description
    row.enabled = data.enabled
    row.media_file_id = data.media_file_id
    audit(db, None, 'home-banner-saved', 'home_banner')
    db.flush()
    return home(db)['banner']

def list_promotions(db):
    return home(db)['promotions']

def save_promotion(db, data, promotion_id=None):
    payload = data.model_dump()
    if payload['ends_at'] and payload['starts_at'] and payload['ends_at'] <= payload['starts_at']:
        raise HTTPException(422, 'Promotion end must be after its start')
    row = db.get(Promotion, promotion_id) if promotion_id else None
    if promotion_id and not row:
        raise HTTPException(404, 'Promotion not found')
    if not row:
        row = Promotion()
        db.add(row)
    for key, value in payload.items():
        setattr(row, key, value.upper() if key == 'code' else value)
    db.flush()
    audit(db, None, 'promotion-saved', f'promotion:{row.id}')
    return row

def delete_promotion(db, promotion_id):
    row = db.get(Promotion, promotion_id)
    if not row:
        raise HTTPException(404, 'Promotion not found')
    audit(db, None, 'promotion-deleted', f'promotion:{row.id}')
    db.delete(row)
    return {'deleted': promotion_id}

def _order(db, user, order_id):
    return order_service.owned(db, user, order_id)

def create_ticket(db, user, data):
    if data.order_id is not None:
        _order(db, user, data.order_id)
    row = SupportTicket(user_id=user.id, order_id=data.order_id, subject=data.subject, description=data.description)
    db.add(row)
    db.flush()
    audit(db, user.id, 'support-ticket-created', f'ticket:{row.id}')
    return ticket_data(db, row)

def ticket_data(db, row):
    owner = db.get(User, row.user_id)
    return {
        'id': row.id, 'order_id': row.order_id, 'subject': row.subject, 'description': row.description,
        'status': row.status, 'resolution': row.resolution, 'created_at': row.created_at,
        'updated_at': row.updated_at, 'user_name': owner.name if owner else '',
    }

def tickets(db, user):
    rows = list(db.scalars(select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.id.desc()).limit(200)))
    return [ticket_data(db, row) for row in rows]

def all_tickets(db):
    rows = list(db.scalars(select(SupportTicket).order_by(SupportTicket.id.desc()).limit(300)))
    return [ticket_data(db, row) for row in rows]

def update_ticket(db, ticket_id, data):
    row = db.get(SupportTicket, ticket_id)
    if not row:
        raise HTTPException(404, 'Ticket not found')
    row.status = data.status
    row.resolution = data.resolution
    notify(db, row.user_id, 'support', f'Support ticket #{row.id} is {row.status}.', row.order_id)
    audit(db, None, 'support-ticket-updated', f'ticket:{row.id}')
    db.flush()
    return ticket_data(db, row)

def messages(db, user, order_id):
    _order(db, user, order_id)
    rows = list(db.scalars(select(OrderMessage).where(OrderMessage.order_id == order_id).order_by(OrderMessage.id).limit(500)))
    return [
        {'id': row.id, 'body': row.body, 'created_at': row.created_at, 'user_id': row.user_id,
         'user_name': (db.get(User, row.user_id).name if db.get(User, row.user_id) else '')}
        for row in rows
    ]

def send_message(db, user, order_id, data):
    order = _order(db, user, order_id)
    row = OrderMessage(order_id=order.id, user_id=user.id, body=data.body)
    db.add(row)
    for participant in {order.customer_id, order.restaurant_id, order.driver_id} - {None, user.id}:
        notify(db, participant, 'order-message', f'New message for order #{order.id}.', order.id)
    audit(db, user.id, 'order-message-sent', f'order:{order.id}')
    db.flush()
    return {'id': row.id, 'body': row.body, 'created_at': row.created_at, 'user_id': user.id, 'user_name': user.name}

def notifications(db, user):
    rows = list(db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(100)))
    return [{'id': row.id, 'kind': row.kind, 'body': row.body, 'order_id': row.order_id, 'read_at': row.read_at, 'created_at': row.created_at} for row in rows]

def mark_notification(db, user, notification_id):
    row = db.get(Notification, notification_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, 'Notification not found')
    if not row.read_at:
        row.read_at = utcnow()
    return {'id': row.id, 'read_at': row.read_at}

def audit_events(db):
    rows = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(300)))
    return [{'id': row.id, 'actor_id': row.actor_id, 'action': row.action, 'target': row.target, 'details': row.details, 'created_at': row.created_at} for row in rows]


def _admin_user_data(user, restaurant=None, driver=None, customer=None):
    data = {'id': user.id, 'role': user.role, 'email': user.email, 'name': user.name, 'phone': user.phone or ''}
    if user.role == 'customer':
        data.update(order_mode=customer.order_mode if customer else 'delivery')
    elif user.role == 'restaurant':
        data.update(
            restaurant_name=restaurant.name if restaurant else user.name,
            description=(restaurant.description or '') if restaurant else '',
            cuisine=restaurant.cuisine if restaurant else '',
            kind=restaurant.kind if restaurant else 'restaurant',
            address=(restaurant.address or '') if restaurant else '',
            is_open=bool(restaurant and restaurant.is_open),
            opening=restaurant.opening if restaurant else '09:00',
            closing=restaurant.closing if restaurant else '22:00',
            delivery_minutes=restaurant.delivery_minutes if restaurant else 30,
        )
    elif user.role == 'driver':
        data.update(
            online=bool(driver and driver.online),
            vehicle_type=(driver.vehicle_type or '') if driver else '',
            vehicle_number=(driver.vehicle_number or '') if driver else '',
        )
    return data


def admin_users(db, q='', role_name='', status=''):
    role_name = role_name.strip().lower()
    if role_name and role_name not in {'customer', 'restaurant', 'driver'}:
        raise HTTPException(422, 'Invalid role')
    stmt = (
        select(User, Restaurant, Driver, Customer)
        .outerjoin(Restaurant, Restaurant.id == User.id)
        .outerjoin(Driver, Driver.id == User.id)
        .outerjoin(Customer, Customer.id == User.id)
    )
    if role_name:
        stmt = stmt.where(User.role == role_name)
    query = q.strip().lower()
    if query:
        pattern = f'%{query}%'
        stmt = stmt.where(or_(
            func.lower(User.name).like(pattern), func.lower(User.email).like(pattern),
            func.lower(func.coalesce(User.phone, '')).like(pattern),
            func.lower(func.coalesce(Restaurant.name, '')).like(pattern),
            func.lower(func.coalesce(Restaurant.cuisine, '')).like(pattern),
            func.lower(func.coalesce(Restaurant.address, '')).like(pattern),
            func.lower(func.coalesce(Driver.vehicle_type, '')).like(pattern),
            func.lower(func.coalesce(Driver.vehicle_number, '')).like(pattern),
        ))
    if status == 'open':
        stmt = stmt.where(Restaurant.is_open == True)
    elif status == 'closed':
        stmt = stmt.where(Restaurant.is_open == False)
    elif status == 'online':
        stmt = stmt.where(Driver.online == True)
    elif status == 'offline':
        stmt = stmt.where(Driver.online == False)
    elif status in {'delivery', 'pickup'}:
        stmt = stmt.where(Customer.order_mode == status)
    rows = db.execute(stmt.order_by(User.id.desc()).limit(500)).all()
    return [_admin_user_data(*row) for row in rows]


def admin_create_user(db, data):
    from backend.services.auth_service import passwords
    payload = data.model_dump()
    email = str(payload['email']).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    user = User(email=email, password=passwords.hash(payload['password']), role=payload['role'], name=payload['name'].strip(), phone=payload['phone'].strip())
    db.add(user)
    db.flush()
    restaurant = driver = customer = None
    if user.role == 'customer':
        customer = Customer(id=user.id, order_mode=payload['order_mode'])
        db.add(customer)
    elif user.role == 'restaurant':
        restaurant = Restaurant(
            id=user.id, name=(payload['restaurant_name'].strip() or user.name),
            description=payload['description'].strip(), cuisine=payload['cuisine'].strip() or 'Indian',
            kind=payload['kind'], address=payload['address'].strip(), is_open=payload['is_open'],
            opening=payload['opening'], closing=payload['closing'], delivery_minutes=payload['delivery_minutes'],
        )
        db.add(restaurant)
    else:
        driver = Driver(id=user.id, online=payload['online'], vehicle_type=payload['vehicle_type'].strip(), vehicle_number=payload['vehicle_number'].strip())
        db.add(driver)
    db.flush()
    audit(db, None, 'admin-user-created', f'user:{user.id}', f'role={user.role}')
    return _admin_user_data(user, restaurant, driver, customer)


def admin_update_user(db, user_id, data):
    from backend.services.auth_service import passwords
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'User not found')
    payload = data.model_dump(exclude_unset=True)
    if 'email' in payload:
        email = str(payload['email']).strip().lower()
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != user.id))
        if duplicate:
            raise HTTPException(409, 'Email already registered')
        user.email = email
    for key in ('name', 'phone'):
        if key in payload:
            setattr(user, key, payload[key].strip())
    if payload.get('password'):
        user.password = passwords.hash(payload['password'])
        user.token_version += 1
    restaurant = db.get(Restaurant, user.id) if user.role == 'restaurant' else None
    driver = db.get(Driver, user.id) if user.role == 'driver' else None
    customer = db.get(Customer, user.id) if user.role == 'customer' else None
    if restaurant:
        field_map = {'restaurant_name': 'name', 'description': 'description', 'cuisine': 'cuisine', 'kind': 'kind', 'address': 'address', 'is_open': 'is_open', 'opening': 'opening', 'closing': 'closing', 'delivery_minutes': 'delivery_minutes'}
        for source, target in field_map.items():
            if source in payload:
                value = payload[source]
                setattr(restaurant, target, value.strip() if isinstance(value, str) else value)
    if driver:
        for key in ('online', 'vehicle_type', 'vehicle_number'):
            if key in payload:
                value = payload[key]
                setattr(driver, key, value.strip() if isinstance(value, str) else value)
    if customer and 'order_mode' in payload:
        customer.order_mode = payload['order_mode']
    db.flush()
    audit(db, None, 'admin-user-updated', f'user:{user.id}', ','.join(sorted(key for key in payload if key != 'password')))
    return _admin_user_data(user, restaurant, driver, customer)


def _delete_order_records(db, order_ids):
    if not order_ids:
        return
    for model in (DeliveryStatus, Rating, Review, OrderItem, OrderMessage, Notification, SupportTicket):
        db.execute(delete(model).where(model.order_id.in_(order_ids)))
    db.execute(delete(Order).where(Order.id.in_(order_ids)))


def admin_delete_user(db, user_id):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'User not found')
    role_name = user.role
    if role_name == 'customer':
        order_ids = list(db.scalars(select(Order.id).where(Order.customer_id == user_id)))
        _delete_order_records(db, order_ids)
        db.execute(delete(Review).where(Review.customer_id == user_id))
        db.execute(delete(CartItem).where(CartItem.customer_id == user_id))
        db.execute(delete(Address).where(Address.customer_id == user_id))
        db.execute(delete(CustomerLocation).where(CustomerLocation.customer_id == user_id))
        db.execute(delete(Customer).where(Customer.id == user_id))
    elif role_name == 'restaurant':
        order_ids = list(db.scalars(select(Order.id).where(Order.restaurant_id == user_id)))
        _delete_order_records(db, order_ids)
        menu_ids = list(db.scalars(select(MenuItem.id).where(MenuItem.restaurant_id == user_id)))
        if menu_ids:
            db.execute(delete(CartItem).where(CartItem.menu_item_id.in_(menu_ids)))
        db.execute(delete(RestaurantPresentation).where(RestaurantPresentation.restaurant_id == user_id))
        db.execute(delete(MenuItem).where(MenuItem.restaurant_id == user_id))
        db.execute(delete(Restaurant).where(Restaurant.id == user_id))
    elif role_name == 'driver':
        db.execute(update(Order).where(Order.driver_id == user_id).values(driver_id=None))
        db.execute(delete(DriverLocation).where(DriverLocation.driver_id == user_id))
        db.execute(delete(Driver).where(Driver.id == user_id))
    else:
        raise HTTPException(422, 'Unsupported user role')
    file_ids = select(File.id).where(File.user_id == user_id)
    db.execute(update(PlatformContent).where(PlatformContent.media_file_id.in_(file_ids)).values(media_file_id=None))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
    db.execute(delete(OrderMessage).where(OrderMessage.user_id == user_id))
    db.execute(delete(Notification).where(Notification.user_id == user_id))
    db.execute(delete(SupportTicket).where(SupportTicket.user_id == user_id))
    db.execute(update(AuditEvent).where(AuditEvent.actor_id == user_id).values(actor_id=None))
    db.execute(delete(File).where(File.user_id == user_id))
    db.delete(user)
    audit(db, None, 'admin-user-deleted', f'user:{user_id}', f'role={role_name}')
    return {'deleted': user_id, 'role': role_name}
