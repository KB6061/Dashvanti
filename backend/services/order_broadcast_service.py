import asyncio
import json
import logging
import time
from datetime import datetime
from sqlalchemy import event, select, inspect
from backend.db import Session
from backend.models import Order, DeliveryStatus
from backend.models_order_stream import OrderBroadcastEvent
from backend.services import redis_geo_service as geo

CHANNEL = 'order_updates'
log = logging.getLogger('dashvanti.orders')
ALIASES = {'READY_FOR_PICKUP': 'READY', 'ON_THE_WAY_TO_CUSTOMER': 'DELIVERING', 'DELIVERED': 'COMPLETED'}


def broadcast_order_update(order_id, status, timestamp=None, db=None):
    if db is None:
        with Session() as session:
            row = broadcast_order_update(order_id, status, timestamp, session)
            session.commit()
            return row.payload
    order = db.get(Order, order_id)
    if not order:
        return None
    from backend.services.customer_queue_tracking_service import state
    row = OrderBroadcastEvent(order_id=order_id, payload={
        'queue': state(db, order),
        'type': 'order_update', 'order_id': order_id, 'status': ALIASES.get(status, status),
        'canonical_status': order.status, 'activity_status': status,
        'timestamp': timestamp or time.time(), 'customer_id': order.customer_id,
        'restaurant_id': order.restaurant_id, 'driver_id': order.driver_id,
    })
    db.add(row)
    return row


def install():
    cls = Session.class_
    if getattr(cls, '_order_stream_installed', False):
        return
    cls._order_stream_installed = True

    @event.listens_for(cls, 'before_flush')
    def collect(db, *_):
        pending = db.info.setdefault('order_stream_pending', [])
        for row in list(db.new) + list(db.dirty):
            if isinstance(row, Order) and (row in db.new or db.is_modified(row, include_collections=False)):
                pending.append(row)
            elif isinstance(row, DeliveryStatus) and row in db.new:
                pending.append(row)

    @event.listens_for(cls, 'before_commit')
    def prepare(db):
        if db.in_nested_transaction():
            return
        db.flush()
        pending = db.info.pop('order_stream_pending', [])
        updates = {}
        for row in sorted(pending, key=lambda value: isinstance(value, DeliveryStatus)):
            if isinstance(row, DeliveryStatus) and not inspect(row).persistent:
                continue
            updates[row.id if isinstance(row, Order) else row.order_id] = row.status
        from backend.models_driver_queue import DriverUpcomingOrder
        affected = {order.driver_id for uid in updates if (order := db.get(Order, uid)) and order.driver_id}
        if affected:
            for reservation in db.scalars(select(DriverUpcomingOrder).where(DriverUpcomingOrder.driver_id.in_(affected))):
                updates.setdefault(reservation.order_id, 'DRIVER_QUEUED')
        records = [broadcast_order_update(uid, status, db=db) for uid, status in updates.items()]
        db.flush()
        db.info['order_stream_publish'] = [{**row.payload, 'event_id': row.id} for row in records if row]

    @event.listens_for(cls, 'after_commit')
    def publish(db):
        if db.in_nested_transaction():
            return
        for data in db.info.pop('order_stream_publish', []):
            try:
                geo.client().publish(CHANNEL, json.dumps(data))
            except Exception:
                log.warning('Order broadcast queued for retry: %s', data['order_id'])
        db.info.pop('order_stream_pending', None)

    @event.listens_for(cls, 'after_rollback')
    def rollback(db):
        if db.in_nested_transaction():
            return
        db.info.pop('order_stream_pending', None)
        db.info.pop('order_stream_publish', None)


def pending_batch():
    with Session() as db:
        rows = db.scalars(select(OrderBroadcastEvent).where(OrderBroadcastEvent.published_at.is_(None)).order_by(OrderBroadcastEvent.id).limit(100).with_for_update(skip_locked=True))
        for row in rows:
            geo.client().publish(CHANNEL, json.dumps({**row.payload, 'event_id': row.id}))
            row.published_at = datetime.utcnow()
        db.commit()


async def retry(redis, manager):
    while True:
        await asyncio.to_thread(pending_batch)
        await asyncio.sleep(1)


async def subscribe(redis, manager):
    from redis.asyncio import Redis
    from backend.gps_config import REDIS_URL
    connection = Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=None)
    try:
        async with connection.pubsub() as subscriber:
            await subscriber.subscribe(CHANNEL)
            async for message in subscriber.listen():
                if message['type'] == 'message':
                    await manager.order_update(json.loads(message['data']))
    finally:
        await connection.aclose()
