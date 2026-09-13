import os
import re
import time
from decimal import Decimal, InvalidOperation
from threading import Lock

import httpx
from fastapi import HTTPException

ZIP_RE = re.compile(r'^\d{5}(?:-\d{4})?$')
_CACHE: dict[str, tuple[float, Decimal]] = {}
_LOCK = Lock()
TTL_SECONDS = 900

def get_us_tax_rate(zip_code: str) -> Decimal:
    if not ZIP_RE.fullmatch(zip_code):
        raise HTTPException(422, 'customer_zip must be a valid US ZIP code')
    key = zip_code[:5]
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
    api_key = os.environ.get('TAX_API_KEY')
    if not api_key:
        raise HTTPException(503, 'Tax service is not configured')
    try:
        response = httpx.get(
            f'https://api.example.com/v2/rates/{key}',
            headers={'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'},
            timeout=5,
        )
        response.raise_for_status()
        combined_rate = response.json()['rate']['combined_rate']
        rate = Decimal(str(combined_rate))
    except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation):
        raise HTTPException(503, 'Tax service is temporarily unavailable')
    if rate < 0 or rate > 1:
        raise HTTPException(503, 'Tax service returned an invalid rate')
    with _LOCK:
        _CACHE[key] = (time.monotonic() + TTL_SECONDS, rate)
    return rate
