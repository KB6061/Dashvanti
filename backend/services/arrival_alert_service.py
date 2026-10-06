import asyncio
import json
import math
import time
from sqlalchemy import select
from backend.db import Session
from backend.models import Driver, Order
from backend.gps_config import FINAL
from backend.services import redis_geo_service as geo
from backend.services.tracking_service import states

CUSTOMER_LEG = {'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER', 'ARRIVED_AT_CUSTOMER'}


def _owner(order_id, driver_id):
    with Session() as db:
        order, driver = db.get(Order, order_id), db.get(Driver, driver_id)
        if not order or not driver or not driver.online or order.mode != 'delivery':
            return None
        if order.driver_id != driver_id or order.status in FINAL:
            return None
        return order.customer_id if states(db, order)[1] in CUSTOMER_LEG else None


def _orders(customer_id, order_id=None):
    with Session() as db:
        query = select(Order).join(Driver, Driver.id == Order.driver_id).where(
            Order.customer_id == customer_id, Order.mode == 'delivery',
            Order.status.not_in(FINAL), Driver.online.is_(True),
        )
        if order_id is not None:
            query = query.where(Order.id == order_id)
        return [(order.id, order.driver_id) for order in db.scalars(query.limit(20))
                if states(db, order)[1] in CUSTOMER_LEG]


async def publish(redis, navigation):
    if navigation.get('stage') != 'customer':
        return False
    try:
        seconds, distance = float(navigation['eta_seconds']), float(navigation['distance_meters'])
        age = time.time() * 1000 - float(navigation['timestamp'])
        accuracy = float(navigation.get('accuracy') or 15)
        gap = float(navigation.get('route_gap_meters', 0))
        order_id, driver_id = int(navigation['order_id']), int(navigation['driver_id'])
        if not all(math.isfinite(value) for value in (seconds, distance, age, accuracy, gap)):
            return False
        if min(seconds, distance, accuracy, gap) < 0 or not -5000 <= age <= 12000:
            return False
        if accuracy > 100 or gap > max(40, accuracy * 1.5):
            return False
        if seconds > 120 and distance > 300:
            return False
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    key = f'arrival:sent:{order_id}:{driver_id}'
    previous = await redis.get(key)
    customer_id = int(previous) if previous else await asyncio.to_thread(_owner, order_id, driver_id)
    if customer_id is None:
        return False
    if navigation.get('customer_id') not in (None, customer_id):
        return False
    event = {
        'type': 'driver_arriving', 'event': 'driver_arriving',
        'event_id': f'arrival:{order_id}:{driver_id}', 'order_id': order_id,
        'driver_id': driver_id, 'customer_id': customer_id,
        'eta': round(seconds / 60, 2), 'distance': round(distance),
        'timestamp': navigation['timestamp'],
    }
    encoded = json.dumps(event)
    await redis.set(f'arrival:current:{order_id}:{driver_id}', encoded, ex=45)
    if not await redis.set(key, str(customer_id), nx=True, ex=7 * 86400):
        return False
    try:
        await redis.publish(geo.CHANNEL, encoded)
    except Exception:
        await redis.delete(key)
        raise
    return True


async def pending(redis, customer_id, order_id=None):
    orders = await asyncio.to_thread(_orders, customer_id, order_id)
    if not orders:
        return []
    values = await redis.mget([f'arrival:current:{oid}:{driver}' for oid, driver in orders])
    events = []
    for value in values:
        if not value:
            continue
        data = json.loads(value)
        if data.get('customer_id') == customer_id and time.time() * 1000 - data['timestamp'] <= 45000:
            events.append(data)
    return events
