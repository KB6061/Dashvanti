from fastapi import HTTPException
from sqlalchemy import select, update
from backend.models import Address, Customer, CustomerLocation, User

def update_profile(db, user, data):
    values = data.model_dump()
    if user.role == 'customer' and ((values.get('email') and str(values['email']).lower() != user.email.lower()) or ('phone' in values and values['phone'] != user.phone)):
        raise HTTPException(403, 'Update email or mobile through My Account with password confirmation')
    country = values.pop('country', None)
    if country:
        from backend.services.geo_service import normalize_country
        normalized = normalize_country(country)
        if country and not normalized:
            raise HTTPException(400, 'Use India or a two-letter country code')
        user.country = normalized
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
    changed = row.details != data.details
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    if changed:
        row.country = row.state = row.city = row.latitude = row.longitude = None
        from backend.services.restaurant_location_service import geocode
        found = geocode(address=row.details) or {}
        for key in ('country', 'state', 'city', 'latitude', 'longitude'):
            if found.get(key) is not None:
                setattr(row, key, found[key])
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
    detected=False
    if data.address is None and (location is None or not location.address):
        from backend.services.restaurant_location_service import geocode
        found=geocode(latlng=f'{data.latitude},{data.longitude}') or {}
        address=('Near '+found['address'])[:500] if found.get('address') else f'{data.latitude:.5f}, {data.longitude:.5f}'
        data=data.model_copy(update={'address':address,'country':found.get('country') or data.country})
        detected=True
    unchanged = location is not None and location.latitude == data.latitude and location.longitude == data.longitude
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
    from backend.services.geo_service import normalize_country
    country=normalize_country(data.country)
    if country or not unchanged:
        location.country=country
    if country and not user.country:user.country=country
    if detected and not db.scalar(select(Address.id).where(Address.customer_id==user.id)):
        db.add(Address(customer_id=user.id,label='Current location',details=data.address,is_default=True))
    db.flush()
    return {
        'country': location.country,
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
