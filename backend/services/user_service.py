from fastapi import HTTPException
from sqlalchemy import select, update
from backend.models import Address, Customer, CustomerLocation, User

def update_profile(db, user, data):
    values = data.model_dump()
    email = values.pop('email', None)
    if email:
        email = str(email).lower()
        existing = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if existing:
            raise HTTPException(409, 'Email already registered')
        user.email = email
    for key, value in values.items():
        setattr(user, key, value)
    return {'message': 'Profile saved'}

def addresses(db, user):
    return list(db.scalars(select(Address).where(Address.customer_id == user.id).order_by(Address.is_default.desc(), Address.id)))

def save_address(db, user, data, address_id=None):
    db.scalar(select(Customer).where(Customer.id == user.id).with_for_update())
    row = db.get(Address, address_id) if address_id else Address(customer_id=user.id)
    if not row or row.customer_id != user.id:
        raise HTTPException(404, 'Address not found')
    if data.is_default:
        db.execute(update(Address).where(Address.customer_id == user.id).values(is_default=False))
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return row

def delete_address(db, user, address_id):
    row = db.get(Address, address_id)
    if not row or row.customer_id != user.id:
        raise HTTPException(404, 'Address not found')
    db.delete(row)
    return {'message': 'Address removed'}


def save_order_mode(db, user, data):
    customer = db.get(Customer, user.id)
    if not customer:
        raise HTTPException(404, 'Customer not found')
    customer.order_mode = data.mode
    db.flush()
    return {'mode': customer.order_mode}


def current_location(db, user):
    return db.get(CustomerLocation, user.id)

def save_current_location(db, user, data):
    location = db.get(CustomerLocation, user.id)
    if not location:
        location = CustomerLocation(
            customer_id=user.id,
            latitude=data.latitude,
            longitude=data.longitude,
            address=data.address.strip() if data.address else None,
        )
        db.add(location)
    else:
        location.latitude = data.latitude
        location.longitude = data.longitude
        if data.address is not None:
            location.address = data.address.strip() or None
    db.flush()
    return {
        'latitude': location.latitude,
        'longitude': location.longitude,
        'address': location.address,
        'updated_at': location.updated_at,
    }

def set_order_sound(db, user, enabled):
    user.order_sound_enabled = enabled
    db.add(user)
    db.flush()
    return {'enabled': bool(user.order_sound_enabled), 'user_id': user.id}
