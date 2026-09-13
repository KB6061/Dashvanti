import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import Address, CartItem, MenuItem, Restaurant

_cache = {}
def waypoint(value):
    if isinstance(value, tuple) and len(value) == 2:
        lat, lng = value
        if not all(isinstance(n, (int, float)) and math.isfinite(n) for n in value) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise HTTPException(422, 'Invalid coordinates')
        return {'location': {'latLng': {'latitude': lat, 'longitude': lng}}}
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(422, 'Address is required')
    return {'address': value.strip()}

def route(origin, destination):
    origin_waypoint, destination_waypoint = waypoint(origin), waypoint(destination)
    key = (origin, destination)
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    if not api_key:
        raise HTTPException(503, 'Route estimate unavailable')
    try:
        response = httpx.post('https://routes.googleapis.com/directions/v2:computeRoutes',
            headers={'X-Goog-Api-Key': api_key, 'X-Goog-FieldMask': 'routes.duration,routes.distanceMeters'},
            json={'origin': origin_waypoint, 'destination': destination_waypoint,
                  'travelMode': 'DRIVE', 'routingPreference': 'TRAFFIC_AWARE'}, timeout=10)
        response.raise_for_status()
        found = response.json().get('routes', [])
        if not found:
            raise ValueError('No route')
        meters = float(found[0]['distanceMeters'])
        seconds = float(found[0]['duration'].removesuffix('s'))
        if not math.isfinite(meters) or not math.isfinite(seconds) or meters < 0 or seconds < 0:
            raise ValueError('Invalid route result')
        result = {'drive_minutes': math.ceil(seconds / 60),
                  'distance_meters': meters, 'distance_miles': round(meters / 1609.344, 2),
                  'distance_type': 'driving'}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Driving estimate unavailable. Please try again.')
    if len(_cache) >= 500:
        _cache.clear()
    _cache[key] = (time.monotonic() + 120, result)
    return result

def checkout_eta(db, user, address_id, mode):
    restaurants = list(db.scalars(select(Restaurant).where(Restaurant.id.in_(
        select(MenuItem.restaurant_id).join(CartItem, CartItem.menu_item_id == MenuItem.id)
        .where(CartItem.customer_id == user.id)))))
    if not restaurants:
        raise HTTPException(400, 'Cart is empty')
    if mode not in {'delivery', 'pickup'}:
        raise HTTPException(422, 'Invalid mode')
    address = db.get(Address, address_id) if address_id else None
    if mode == 'delivery' and (not address or address.customer_id != user.id):
        raise HTTPException(400, 'Choose a delivery address')
    def estimate(restaurant):
        travel = route(restaurant.address, address.details) if mode == 'delivery' and restaurant.address else None
        if mode == 'delivery' and not travel:
            raise HTTPException(409, 'Restaurant address is missing')
        prep = restaurant.delivery_minutes or 30
        return {'restaurant_id': restaurant.id, 'restaurant_name': restaurant.name,
                'minutes': prep + (travel['drive_minutes'] if travel else 0),
                'preparation_minutes': prep, **(travel or {})}
    with ThreadPoolExecutor(max_workers=4) as pool:
        groups = list(pool.map(estimate, restaurants))
    return {'mode': mode, 'minutes': max(g['minutes'] for g in groups), 'groups': groups}
