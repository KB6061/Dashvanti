import hashlib
import hmac
import ipaddress
import os
import time
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from backend.models import CustomerLocation
from backend.customer_account_models import CustomerProfile

STATES = {
    'US': ['Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut','Delaware','District of Columbia','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan','Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota','Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming'],
    'IN': ['Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh','Goa','Gujarat','Haryana','Himachal Pradesh','Jharkhand','Karnataka','Kerala','Madhya Pradesh','Maharashtra','Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan','Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand','West Bengal','Andaman and Nicobar Islands','Chandigarh','Dadra and Nagar Haveli and Daman and Diu','Delhi','Jammu and Kashmir','Ladakh','Lakshadweep','Puducherry'],
}


def client_ip(request):
    address = request.client.host if request.client else ''
    signed = request.headers.get('x-dashvanti-client-ip', '')
    timestamp = request.headers.get('x-dashvanti-ip-time', '')
    signature = request.headers.get('x-dashvanti-ip-signature', '')
    key = os.environ.get('PAYMENT_PROXY_SECRET', '')
    if key and signed and timestamp:
        expected = hmac.new(key.encode(), f'{timestamp}:{signed}'.encode(), hashlib.sha256).hexdigest()
        try:
            if abs(time.time() - int(timestamp)) < 60 and hmac.compare_digest(expected, signature):
                address = signed
        except ValueError:
            pass
    return address


@lru_cache(maxsize=1)
def reader():
    path = os.environ.get('GEOIP_CITY_DATABASE_PATH')
    if not path:
        return None
    import geoip2.database
    return geoip2.database.Reader(path)


def ip_profile(request):
    try:
        address = client_ip(request)
        if not ipaddress.ip_address(address).is_global or not reader():
            return None
        city = reader().city(address)
        return {'country': city.country.iso_code, 'city': city.city.name or '',
                'state': city.subdivisions.most_specific.name or '', 'timezone': city.location.time_zone}
    except (ValueError, OSError, KeyError):
        return None
    except Exception:
        return None


def detect(db, user, data):
    from backend.services.customer_account_service import record
    from backend.services.restaurant_location_service import geocode
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, 'Invalid timezone')
    found = geocode(latlng=f'{data.latitude},{data.longitude}')
    if not found or found.get('country') not in STATES:
        raise HTTPException(422, 'Choose a supported delivery address; location could not be confirmed')
    profile = record(db, CustomerProfile, user)
    user.country = found['country']
    profile.city, profile.state = found.get('city', ''), found.get('state', '')
    profile.timezone, profile.timezone_detected, profile.language = data.timezone, True, data.language
    location = db.get(CustomerLocation, user.id)
    if not location:
        location = CustomerLocation(customer_id=user.id)
        db.add(location)
    for name in ('latitude', 'longitude', 'country'):
        setattr(location, name, found[name])
    location.address = found.get('address', '')
    db.flush()
    return {'country': user.country, 'city': profile.city, 'state': profile.state, 'timezone': profile.timezone}
