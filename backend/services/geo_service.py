import hashlib
import hmac
import ipaddress
import os
import time
from functools import lru_cache


def normalize_country(value):
    value = (value or '').strip().upper()
    if value == 'INDIA':
        return 'IN'
    if value in {'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA'}:
        return 'US'
    return value if len(value) == 2 and value.isascii() and value.isalpha() else None


@lru_cache(maxsize=1)
def geo_reader():
    path = os.environ.get('GEOIP_DATABASE_PATH', '')
    if not path:
        return None
    import geoip2.database
    return geoip2.database.Reader(path)


def detect_country(request, user):
    country = normalize_country(getattr(user, 'country', None))
    if country:
        return country
    address = request.client.host if request.client else ''
    forwarded = request.headers.get('x-dashvanti-client-ip', '')
    timestamp = request.headers.get('x-dashvanti-ip-time', '')
    signature = request.headers.get('x-dashvanti-ip-signature', '')
    key = os.environ.get('PAYMENT_PROXY_SECRET', '')
    if key and forwarded and timestamp:
        expected = hmac.new(key.encode(), f'{timestamp}:{forwarded}'.encode(), hashlib.sha256).hexdigest()
        try:
            if abs(time.time() - int(timestamp)) < 60 and hmac.compare_digest(expected, signature):
                address = forwarded
        except ValueError:
            pass
    try:
        if not ipaddress.ip_address(address).is_global:
            return None
        reader = geo_reader()
        return reader.country(address).country.iso_code if reader else None
    except (ValueError, OSError):
        return None
    except Exception:
        return None
