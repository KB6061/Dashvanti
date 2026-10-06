from sqlalchemy import select
from fastapi import HTTPException
from backend.models import Driver, DriverLocation, Order, SystemConfig, now

FINAL = ('DELIVERED', 'REJECTED', 'CANCELLED', 'CANCELED')

def active_delivery(db, driver_id):
    return db.scalar(select(Order.id).where(Order.driver_id == driver_id, Order.status.notin_(FINAL)).limit(1))

def current(db, user):
    driver = db.get(Driver, user.id)
    if not driver:
        raise HTTPException(404, 'Driver not found')
    config = db.get(SystemConfig, f'driver_presence:{user.id}')
    mode = 'ONLINE' if driver.online else ('BREAK' if config and config.value == 'BREAK' else 'HOME')
    from backend.services.redis_geo_service import location as live_location
    location = live_location(db,user.id)
    return {'mode': mode, 'online': bool(driver.online), 'active_delivery': bool(active_delivery(db, user.id)),
            'location': {'latitude': location.latitude, 'longitude': location.longitude, 'heading': location.heading, 'speed': location.speed, 'updated_at': location.updated_at.isoformat() if location and location.updated_at else None} if location else None}

def update(db, user, mode):
    if mode == 'ONLINE':
        from backend.services.driver_partner_service import ensure_active
        ensure_active(db, user.id)
    driver = db.scalar(select(Driver).where(Driver.id == user.id).with_for_update())
    if not driver:
        raise HTTPException(404, 'Driver not found')
    if mode == 'HOME' and active_delivery(db, user.id):
        raise HTTPException(409, 'Complete your active delivery before going home')
    driver.online = mode == 'ONLINE'
    if not driver.online:
        from backend.services.redis_geo_service import remove
        remove(user.id)
    key = f'driver_presence:{user.id}'
    config = db.get(SystemConfig, key)
    if config:
        config.value = mode
    else:
        db.add(SystemConfig(key=key, value=mode))
    db.flush()
    return current(db, user)
