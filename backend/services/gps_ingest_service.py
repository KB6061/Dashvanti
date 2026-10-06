import json
import time
from functools import lru_cache
from uuid import uuid4
from fastapi import HTTPException
from confluent_kafka import Producer
from backend.gps_config import BROKERS,TOPIC
from backend.services.gps_auth_service import context
from backend.services import redis_geo_service as geo

@lru_cache(maxsize=1)
def producer():
    return Producer({'bootstrap.servers':BROKERS,'enable.idempotence':True,'compression.type':'gzip','delivery.timeout.ms':5000,'request.timeout.ms':3000})

def ingest_http(user,data):
    from backend.routers.gps_websocket import sample
    metadata=context(user.id)
    coordinates=sample(data.model_dump())
    if not geo.client().set('gps:ingest-rate:'+str(user.id),'1',nx=True,px=3500):
        return {'driver_id':user.id,'throttled':True,'interval_seconds':4}
    event={'type':'driver_location','driver_id':user.id,**metadata,**coordinates,'timestamp':int(time.time()*1000),'event_id':str(uuid4())}
    geo.put(event)
    failed=[]
    producer().produce(TOPIC,key=str(user.id),value=json.dumps(event),on_delivery=lambda error,message:failed.append(error) if error else None)
    if producer().flush(6) or failed:raise HTTPException(503,'GPS stream reconnecting')
    return event
