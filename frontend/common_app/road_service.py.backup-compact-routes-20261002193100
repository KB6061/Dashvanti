import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.core.cache import cache


def cached_result(key):
    try:
        from backend.services.redis_geo_service import client
        value = client().get(key)
        if value is not None:
            return json.loads(value)
    except Exception:
        pass
    return cache.get(key)


def store_result(key, result):
    ttl = 1800 if result['available'] else 60
    cache.set(key, result, ttl)
    try:
        from backend.services.redis_geo_service import client
        client().set(key, json.dumps(result), ex=ttl)
    except Exception:
        pass


def nearby(lat, lng):
    key = f'road-controls:v2:{lat:.2f}:{lng:.2f}'
    cached = cached_result(key)
    if cached is not None:
        return cached
    query = f'[out:json][timeout:8];node(around:2000,{lat:.2f},{lng:.2f})["highway"~"^(traffic_signals|stop)$"];out body;'
    result = {'available': False, 'points': []}
    for endpoint in ('https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'):
        try:
            request = Request(endpoint + '?' + urlencode({'data': query}),
                              headers={'User-Agent': 'Dashvanti/1.0 support@dashvanti.com'})
            with urlopen(request, timeout=7) as response:
                data = json.load(response)
            points = []
            for node in data.get('elements', []):
                latitude, longitude = node.get('lat'), node.get('lon')
                kind = node.get('tags', {}).get('highway')
                if kind not in {'stop', 'traffic_signals'} or latitude is None or longitude is None:
                    continue
                if not math.isfinite(latitude) or not math.isfinite(longitude):
                    continue
                points.append({'id': node['id'], 'lat': latitude, 'lng': longitude, 'kind': kind})
            cosine = math.cos(math.radians(lat))
            points.sort(key=lambda point: (point['lat']-lat)**2 + ((point['lng']-lng)*cosine)**2)
            result = {'available': True, 'points': points[:300]}
            break
        except (OSError, ValueError, KeyError, TypeError):
            continue
    store_result(key, result)
    return result
