import os
import time
import math
from threading import Lock
import httpx

_cache = {}
_lock = Lock()

def encode_polyline(points):
    """Encodes a list of (lat, lng) tuples into a Google Maps Polyline string."""
    result = []
    last_lat = 0
    last_lng = 0

    for lat, lng in points:
        lat_e5 = int(round(lat * 1e5))
        lng_e5 = int(round(lng * 1e5))

        d_lat = lat_e5 - last_lat
        d_lng = lng_e5 - last_lng

        for val in (d_lat, d_lng):
            val = ~(val << 1) if val < 0 else (val << 1)
            while val >= 0x20:
                result.append(chr((0x20 | (val & 0x1f)) + 63))
                val >>= 5
            result.append(chr(val + 63))

        last_lat = lat_e5
        last_lng = lng_e5

    return "".join(result)

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates Haversine distance in meters between two lat/lng coordinates."""
    r = 6371000.0  # Earth radius in meters
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c

def fallback_route(origin_lat, origin_lng, dest_lat, dest_lng, stage='customer'):
    """Generates realistic fallback route polyline, distance, and ETA when API is unreachable."""
    dist_meters = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    # Estimate driving distance with 1.35 urban grid tortuosity factor
    driving_dist_meters = dist_meters * 1.35
    # Estimate urban speed ~ 25 km/h (7.0 m/s)
    speed_mps = 7.0
    eta_seconds = max(180, int(driving_dist_meters / speed_mps))

    points = [(origin_lat, origin_lng), (dest_lat, dest_lng)]

    return {
        'eta_seconds': eta_seconds,
        'distance_meters': int(driving_dist_meters),
        'active_eta_seconds': eta_seconds,
        'active_distance_meters': int(driving_dist_meters),
        'restaurant_location': {'lat': dest_lat, 'lng': dest_lng} if stage == 'restaurant' else None,
        'customer_location': {'lat': dest_lat, 'lng': dest_lng} if stage == 'customer' else None,
        'polyline': encode_polyline(points),
        'stage': stage,
        'fallback': True,
        'estimated': True,
        'distance_source': 'straight_line_estimate'
    }

def route(order, restaurant, location, status, db=None):
    if order.mode != 'delivery' or status in {'DELIVERED', 'CANCELLED', 'CANCELED', 'REJECTED'}:
        return None

    if not location:
        return None
    origin_lat, origin_lng = location['latitude'], location['longitude']

    key = (order.id, order.driver_id, status, restaurant.address, order.address, origin_lat, origin_lng)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

    after_pickup = status in {'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER'}
    stage = 'customer' if after_pickup else 'restaurant'
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')

    result = None
    if api_key and location and not location.get('stale'):
        try:
            params = {
                'origin': f"{origin_lat},{origin_lng}",
                'destination': order.address,
                'mode': 'driving',
                'departure_time': 'now',
                'key': api_key
            }
            if not after_pickup:
                params['waypoints'] = restaurant.address

            response = httpx.get('https://maps.googleapis.com/maps/api/directions/json', params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'OK' and data.get('routes'):
                found = data['routes'][0]
                legs = found['legs']
                result = {
                    'eta_seconds': sum((leg.get('duration_in_traffic') or leg['duration'])['value'] for leg in legs),
                    'distance_meters': sum(leg['distance']['value'] for leg in legs),
                    'active_eta_seconds': (legs[0].get('duration_in_traffic') or legs[0]['duration'])['value'],
                    'active_distance_meters': legs[0]['distance']['value'],
                    'restaurant_location': None if after_pickup else legs[0]['end_location'],
                    'customer_location': legs[-1]['end_location'],
                    'polyline': found['overview_polyline']['points'],
                    'stage': stage,
                    'fallback': False
                }
        except Exception:
            result = None

    if not result:
        if after_pickup:
            destination = None
            if db is not None:
                from sqlalchemy import select
                from backend.models import Address
                address = db.scalar(select(Address).where(Address.customer_id == order.customer_id, Address.details == order.address).order_by(Address.id.desc()).limit(1))
                if address and address.latitude is not None and address.longitude is not None:
                    destination = {'latitude': address.latitude, 'longitude': address.longitude}
            if destination is None:
                from backend.services.restaurant_location_service import geocode
                destination = geocode(address=order.address)
        else:
            destination = {'latitude': restaurant.latitude, 'longitude': restaurant.longitude} if restaurant.latitude is not None and restaurant.longitude is not None else None
            if destination is None:
                from backend.services.restaurant_location_service import geocode
                destination = geocode(address=restaurant.address)
        if destination is None:
            return None
        result = fallback_route(origin_lat, origin_lng, destination['latitude'], destination['longitude'], stage=stage)

    with _lock:
        if len(_cache) >= 500:
            _cache.clear()
        _cache[key] = (time.monotonic() + 20, result)

    return result
