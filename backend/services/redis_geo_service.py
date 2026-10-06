import json
import time
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from functools import lru_cache
from redis import Redis
from redis.exceptions import RedisError
from redis.asyncio import Redis as AsyncRedis
from backend.gps_config import REDIS_URL, TTL, ENABLED

GEO = 'gps:drivers:geo'
EXPIRES = 'gps:drivers:expires'
CHANNEL = 'gps:push'
STORE = '''
local old = redis.call('GET', KEYS[2])
if old and tonumber(cjson.decode(old).timestamp) > tonumber(ARGV[5]) then return 0 end
redis.call('GEOADD', KEYS[1], ARGV[1], ARGV[2], ARGV[3])
redis.call('SET', KEYS[2], ARGV[4], 'EX', ARGV[6])
redis.call('GEOADD', KEYS[4], ARGV[1], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[4], ARGV[6])
redis.call('ZADD', KEYS[3], ARGV[7], ARGV[3])
return 1
'''
CLEAN = '''
local ids = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
for _, id in ipairs(ids) do
 redis.call('ZREM', KEYS[1], id)
 redis.call('ZREM', KEYS[2], id)
end
return ids
'''

@lru_cache(maxsize=1)
def client():
    return Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1, socket_timeout=2)

def async_client():
    return AsyncRedis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=5)

def arguments(data):
    uid=str(data['driver_id'])
    expiry=data['timestamp']/1000+TTL
    return [GEO, 'gps:driver:'+uid, EXPIRES, 'gps:geo:'+uid], [data['longitude'], data['latitude'], uid, json.dumps(data), data['timestamp'], max(1,int(expiry-time.time())), expiry]

def put(data):
    keys,args=arguments(data)
    return client().eval(STORE,len(keys),*keys,*args)

async def put_async(redis,data):
    keys,args=arguments(data)
    return await redis.eval(STORE,len(keys),*keys,*args)

def live(driver_id):
    try:
        raw=client().get('gps:driver:'+str(driver_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None

def location(db,driver_id):
    if not ENABLED:
        from backend.models import DriverLocation
        return db.get(DriverLocation,driver_id)
    from backend.models import Driver
    driver=db.get(Driver,driver_id)
    if not driver or not driver.online:return None
    data=live(driver_id)
    if not data:return None
    return SimpleNamespace(driver_id=driver_id,latitude=data['latitude'],longitude=data['longitude'],heading=data.get('heading'),speed=data.get('speed'),updated_at=datetime.fromtimestamp(data['timestamp']/1000,timezone.utc).replace(tzinfo=None))

def remove(driver_id):
    if not ENABLED:return
    uid=str(driver_id)
    try:
        with client().pipeline() as pipe:
            pipe.delete('gps:driver:'+uid,'gps:geo:'+uid)
            pipe.zrem(GEO,uid);pipe.zrem(EXPIRES,uid)
            pipe.publish(CHANNEL,json.dumps({'type':'driver_offline','driver_id':driver_id}))
            pipe.execute()
    except RedisError:logging.getLogger('dashvanti.gps').warning('GPS cache removal will retry for driver %s',driver_id)
