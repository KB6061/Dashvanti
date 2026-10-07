import time
from backend.db import Session
from backend.models import Order, Driver, User
from backend.gps_config import FINAL
from backend.services import redis_geo_service as geo


def assignment_location(order_id, driver_id):
    with Session() as db:
        order = db.get(Order, order_id)
        driver = db.get(Driver, driver_id)
        if not order or not driver or not driver.online or order.driver_id != driver_id or order.status in FINAL:
            return None
        location = geo.live(driver_id)
        if not location or time.time() * 1000 - location.get('timestamp', 0) > 30000:
            return None
        user = db.get(User, driver_id)
        return {**location, 'type': 'driver_location', 'driver_id': driver_id, 'order_id': order.id,
            'customer_id': order.customer_id, 'restaurant_id': order.restaurant_id, 'status': order.status,
            'driver': {'id': driver_id, 'name': user.name if user else '', 'phone': user.phone if user else '',
                'vehicle_type': driver.vehicle_type, 'vehicle_number': driver.vehicle_number},
            'assignment_snapshot': True}
