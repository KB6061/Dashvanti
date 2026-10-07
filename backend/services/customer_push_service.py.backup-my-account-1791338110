import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.db import Session
from backend.models import Order, User
from backend.models_order_stream import OrderBroadcastEvent
from backend.customer_push_models import CustomerPushDevice, CustomerPushDelivery

log = logging.getLogger('dashvanti.push')
STATUSES = {'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER', 'DELIVERING'}


def delivery_data(event, navigation=None):
    payload = event.payload
    status = payload.get('activity_status') or payload.get('canonical_status') or payload.get('status')
    data = {'type': 'order_update', 'order_id': str(event.order_id), 'status': str(status), 'canonical_status': str(status), 'event_id': str(event.id)}
    if navigation and navigation.get('stage') == 'customer' and time.time() * 1000 - float(navigation.get('timestamp', 0)) < 30000:
        seconds = max(0, int(navigation['eta_seconds']))
        data.update(eta_seconds=str(seconds), arrival_at=datetime.fromtimestamp(time.time() + seconds, timezone.utc).isoformat(), arrival_unix=str(int(time.time() + seconds)))
    return data


def deliver_batch():
    import firebase_admin
    from firebase_admin import messaging
    from backend.services import redis_geo_service as geo
    try:
        firebase_admin.get_app()
    except ValueError:
        # Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS.
        from dotenv import dotenv_values
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or dotenv_values('.env').get('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_path:
            from firebase_admin import credentials
            firebase_admin.initialize_app(credentials.Certificate(credentials_path))
        else:
            firebase_admin.initialize_app()
    now = time.time()
    with Session() as db:
        events = db.scalars(select(OrderBroadcastEvent).order_by(OrderBroadcastEvent.id.desc()).limit(500)).all()
        for event in reversed(events):
            payload = event.payload
            if payload.get('activity_status', payload.get('canonical_status')) not in STATUSES:
                continue
            occurred = float(payload.get('timestamp', 0))
            if not 0 <= now - occurred <= 900:
                continue
            order = db.get(Order, event.order_id)
            if not order or order.status in {'DELIVERED', 'CANCELLED', 'CANCELED', 'REJECTED'}:
                continue
            user = db.get(User, order.customer_id)
            devices = db.scalars(select(CustomerPushDevice).where(CustomerPushDevice.user_id == order.customer_id, CustomerPushDevice.token_version == user.token_version)).all() if user else []
            navigation = None
            try:
                cached = geo.client().get(f'customer:push:navigation:{order.id}')
                navigation = json.loads(cached) if cached else None
            except Exception:
                log.warning('Navigation estimate unavailable for push')
            # Wait briefly for a real customer-leg estimate; never fabricate ETA.
            if not navigation and now - occurred < 20:
                continue
            for device in devices:
                if device.registered_at > datetime.utcfromtimestamp(occurred):
                    continue
                identity = (event.id, device.installation_id)
                if db.get(CustomerPushDelivery, identity):
                    continue
                data = delivery_data(event, navigation)
                data['customer_id'] = str(user.id)
                try:
                    messaging.send(messaging.Message(token=device.token, data=data, android=messaging.AndroidConfig(priority='high', ttl=timedelta(minutes=5))))
                    db.add(CustomerPushDelivery(event_id=event.id, installation_id=device.installation_id))
                    db.commit()
                except messaging.UnregisteredError:
                    db.delete(device)
                    db.commit()
                except Exception as error:
                    db.rollback()
                    log.warning('Push send failed: %s', type(error).__name__)


async def cache_navigation():
    from redis.asyncio import Redis
    from backend.gps_config import REDIS_URL
    from backend.services import redis_geo_service as geo
    connection = Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=None)
    try:
        async with connection.pubsub() as subscriber:
            await subscriber.subscribe(geo.CHANNEL)
            async for message in subscriber.listen():
                if message['type'] != 'message':
                    continue
                data = json.loads(message['data'])
                if data.get('type') == 'navigation' and data.get('stage') == 'customer':
                    await connection.set(f"customer:push:navigation:{data['order_id']}", message['data'], ex=30)
    finally:
        await connection.aclose()


async def run():
    task = asyncio.create_task(cache_navigation())
    try:
        while True:
            if task.done():
                task.result()
            try:
                await asyncio.to_thread(deliver_batch)
            except Exception as error:
                log.warning('Push provider unavailable: %s', type(error).__name__)
            await asyncio.sleep(5)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
