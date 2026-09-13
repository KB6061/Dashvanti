import os
import time
from threading import Lock
import httpx

_cache={}
_lock=Lock()

def route(order, restaurant, location, status):
    if order.mode!='delivery' or status in {'DELIVERED','CANCELLED','CANCELED','REJECTED'}:
        return None
    if not location or location.get('stale'):
        return None
    key=(order.id,order.driver_id,status,restaurant.address,order.address)
    with _lock:
        cached=_cache.get(key)
        if cached and cached[0]>time.monotonic():
            return cached[1]
    api_key=os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        return None
    after_pickup=status in {'PICKED_UP','ON_THE_WAY_TO_CUSTOMER'}
    params={'origin':f"{location['latitude']},{location['longitude']}",'destination':order.address,
            'mode':'driving','departure_time':'now','key':api_key}
    if not after_pickup:
        params['waypoints']=restaurant.address
    result=None
    try:
        response=httpx.get('https://maps.googleapis.com/maps/api/directions/json',params=params,timeout=5)
        response.raise_for_status()
        data=response.json()
        if data.get('status')=='OK' and data.get('routes'):
            found=data['routes'][0]
            legs=found['legs']
            result={'eta_seconds':sum((leg.get('duration_in_traffic') or leg['duration'])['value'] for leg in legs),
                    'distance_meters':sum(leg['distance']['value'] for leg in legs),
                    'active_eta_seconds':(legs[0].get('duration_in_traffic') or legs[0]['duration'])['value'],
                    'active_distance_meters':legs[0]['distance']['value'],
                    'restaurant_location':None if after_pickup else legs[0]['end_location'],
                    'customer_location':legs[-1]['end_location'],
                    'polyline':found['overview_polyline']['points'],
                    'stage':'customer' if after_pickup else 'restaurant'}
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError):
        result=None
    with _lock:
        if len(_cache)>=500:
            _cache.clear()
        _cache[key]=(time.monotonic()+(30 if result else 10),result)
    return result
