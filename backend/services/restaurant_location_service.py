import math
import os
import time
import httpx
from fastapi import HTTPException
from sqlalchemy import false, func, select
from backend.models import CustomerLocation, Restaurant
from backend.services.geo_service import normalize_country, detect_country

RADIUS_MILES = 10
RADIUS_METRES = 16093.44
_geocoding_cache = {}

def geocode(**params):
    cache_key=tuple(sorted(params.items()))
    cached=_geocoding_cache.get(cache_key)
    if cached and cached[0]>time.monotonic():
        return cached[1]
    if len(_geocoding_cache)>1000:
        _geocoding_cache.clear()
    _geocoding_cache[cache_key]=(time.monotonic()+300,None)
    key = os.environ.get('GOOGLE_GEOCODING_API_KEY') or os.environ.get('GOOGLE_MAPS_API_KEY')
    if not key:
        return None
    try:
        headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':'places.location,places.addressComponents,places.types,places.formattedAddress'}
        if 'address' in params:
            endpoint='searchText'
            payload={'textQuery':params['address'],'maxResultCount':1}
        else:
            latitude,longitude=map(float,params['latlng'].split(','))
            endpoint='searchNearby'
            payload={'locationRestriction':{'circle':{'center':{'latitude':latitude,'longitude':longitude},'radius':100}},'maxResultCount':1,'rankPreference':'DISTANCE'}
        response = httpx.post('https://places.googleapis.com/v1/places:'+endpoint,headers=headers,json=payload,timeout=4)
        response.raise_for_status()
        data = response.json()
        result = next(iter(data.get('places',[])),None)
        if not result or ('address' in params and not set(result.get('types',[])).intersection({'street_address','premise','subpremise','establishment','point_of_interest'})):
            return None
        country = next((item['shortText'] for item in result['addressComponents'] if 'country' in item['types']), None)
        point = result['location']
        components = result['addressComponents']
        state = next((item.get('longText', '') for item in components if 'administrative_area_level_1' in item['types']), '')
        city = next((item.get('longText', '') for item in components if set(item['types']).intersection({'locality', 'postal_town', 'administrative_area_level_3'})), '')
        found={'country': normalize_country(country), 'state': state, 'city': city, 'latitude': point['latitude'], 'longitude': point['longitude'],'address':result.get('formattedAddress')}
        _geocoding_cache[cache_key]=(time.monotonic()+3600,found)
        return found
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None

def configure_restaurant(row, values, previous_address=None):
    changed = previous_address is not None and previous_address != row.address
    previous_point=(row.latitude,row.longitude)
    if changed:
        row.country = row.latitude = row.longitude = None
    country = normalize_country(values.get('country'))
    if values.get('country') and not country:
        raise HTTPException(422, 'Use India or a two-letter country code')
    latitude, longitude = values.get('latitude'), values.get('longitude')
    if changed and (latitude,longitude)==previous_point:
        latitude=longitude=None
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, 'Provide both restaurant coordinates')
    if country:
        row.country = country
    if latitude is not None:
        row.latitude, row.longitude = latitude, longitude
    if row.address and (row.country is None or row.latitude is None or row.longitude is None):
        found = geocode(address=row.address)
        if found:
            for name in ('country','latitude','longitude'):
                setattr(row, name, found[name])
            from sqlalchemy.orm import object_session
            from backend.account_enhancement_models import RestaurantRegion
            db=object_session(row)
            if db and found.get('city'):
                region=db.get(RestaurantRegion,row.id)
                if not region:region=RestaurantRegion(restaurant_id=row.id,city=found['city']);db.add(region)
                region.city=found['city'];region.state=found.get('state','')

def customer_scope(db, user, request=None):
    if user is None or user.role != 'customer':
        return None
    location = db.get(CustomerLocation, user.id)
    country = normalize_country(user.country)
    if not location:
        return {'country': country, 'location': None, 'reason': 'location_required'}
    country = normalize_country(location.country)
    if not country:
        found = geocode(latlng=f'{location.latitude},{location.longitude}')
        if found:
            location.country = found['country']
            country = location.country
    if not country and request is not None:
        country = normalize_country(user.country) or detect_country(request, user)
    from backend.customer_account_models import CustomerProfile
    profile=db.get(CustomerProfile,user.id)
    country=normalize_country(user.country) or country
    return {'country': country, 'city':profile.city if profile else '', 'location': location, 'reason': None if country else 'country_required'}

def restrict(stmt, scope):
    if scope is None:
        return stmt
    if scope['reason']:
        return stmt.where(false())
    location = scope['location']
    a = func.power(func.sin(func.radians(Restaurant.latitude - location.latitude) / 2), 2) + func.cos(func.radians(location.latitude)) * func.cos(func.radians(Restaurant.latitude)) * func.power(func.sin(func.radians(Restaurant.longitude - location.longitude) / 2), 2)
    metres = 2 * 6371000 * func.asin(func.sqrt(func.least(1.0, func.greatest(0.0, a))))
    from backend.account_enhancement_models import RestaurantRegion
    if scope.get('city'):
        stmt=stmt.where(Restaurant.id.in_(select(RestaurantRegion.restaurant_id).where(func.lower(RestaurantRegion.city)==scope['city'].lower())))
    return stmt.where(Restaurant.country == scope['country'], Restaurant.latitude.is_not(None), Restaurant.longitude.is_not(None), metres <= RADIUS_METRES)

def metadata(scope):
    if scope is None:
        return {}
    return {'country': scope['country'], 'radius_miles': RADIUS_MILES, 'location_required': scope['reason'] == 'location_required', 'country_required': scope['reason'] == 'country_required'}

def distance_miles(row, scope):
    if scope is None or scope['location'] is None:
        return None
    origin = scope['location']
    a, b = math.radians(origin.latitude), math.radians(row.latitude)
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(row.longitude-origin.longitude)/2)**2
    return round(6371000*2*math.asin(math.sqrt(min(1,h)))/1609.344, 2)
