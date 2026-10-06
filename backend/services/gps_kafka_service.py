import asyncio
import json
import logging
import time
from aiokafka import AIOKafkaProducer,AIOKafkaConsumer
from fastapi import HTTPException
from sqlalchemy import select
from backend.gps_config import BROKERS,TOPIC,TTL
from backend.services import redis_geo_service as geo
from backend.services.gps_auth_service import visible_order,context
from backend.services.gps_point_service import route_point
from backend.db import Session
from backend.models import Order

log=logging.getLogger('dashvanti.gps')

def producer():
    return AIOKafkaProducer(bootstrap_servers=BROKERS,enable_idempotence=True,compression_type='gzip',linger_ms=20,request_timeout_ms=5000,value_serializer=lambda value:json.dumps(value).encode())

def persist_point(data):
    if not data.get('order_id'):return
    with Session() as db:
        order=db.scalar(select(Order).where(Order.id==data['order_id']).with_for_update())
        from backend.gps_config import FINAL
        if not order or order.driver_id!=data['driver_id'] or order.status in FINAL:return
        route_point(db,data)
        from backend.services.arrival_service import detect
        if order.status=='ON_THE_WAY_TO_CUSTOMER':detect(db,order,data['latitude'],data['longitude'])
        db.commit()

async def consume(redis,health):
    consumer=AIOKafkaConsumer(TOPIC,bootstrap_servers=BROKERS,group_id='dashvanti-gps-fanout-v1',auto_offset_reset='latest',enable_auto_commit=False,value_deserializer=lambda raw:json.loads(raw),max_poll_records=100)
    await consumer.start();health['consumer']=True
    try:
        async for message in consumer:
            data=message.value
            if time.time()*1000-data['timestamp']>TTL*1000:
                await consumer.commit();continue
            try:
                metadata=await asyncio.to_thread(context,data['driver_id'])
                if metadata['order_id']!=data.get('order_id'):data={**data,**metadata}
                fresh=await geo.put_async(redis,data)
                if fresh:
                    await redis.publish(geo.CHANNEL,json.dumps(data))
                    if data.get('order_id'):
                        key='gps:point-check:'+str(data['order_id'])
                        if await redis.set(key,'1',nx=True,ex=30):await asyncio.to_thread(persist_point,data)
            except HTTPException:
                await asyncio.to_thread(geo.remove,data['driver_id'])
                await consumer.commit();continue
            except Exception:
                log.exception('GPS consumer processing failed')
                health['consumer']=False
                raise
            await consumer.commit()
    finally:health['consumer']=False;await consumer.stop()

async def fanout(redis,manager):
    from redis.asyncio import Redis
    from backend.gps_config import REDIS_URL
    connection=Redis.from_url(REDIS_URL,decode_responses=True,socket_connect_timeout=2,socket_timeout=None)
    try:
        async with connection.pubsub() as subscriber:
            await subscriber.subscribe(geo.CHANNEL)
            async for message in subscriber.listen():
                if message['type']=='message':await manager.push(json.loads(message['data']))
    finally:await connection.aclose()

async def clean(redis,manager):
    while True:
        ids=await redis.eval(geo.CLEAN,2,geo.GEO,geo.EXPIRES,time.time())
        for uid in ids:await redis.publish(geo.CHANNEL,json.dumps({'type':'driver_offline','driver_id':int(uid)}))
        await asyncio.sleep(5)

async def supervise(function,*args):
    while True:
        try:await function(*args)
        except asyncio.CancelledError:raise
        except Exception:
            log.exception('GPS streaming reconnecting: %s',function.__name__)
            await asyncio.sleep(3)
