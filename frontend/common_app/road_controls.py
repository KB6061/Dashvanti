import math
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .road_service import nearby


@require_GET
def road_controls(request):
    portal = request.path.strip('/').split('/')[0]
    authenticated = request.session.get('admin_authenticated') if portal == 'admin' else (
        portal in {'customer', 'restaurant', 'driver'} and request.session.get('token')
        and request.session.get('role') == portal
    )
    if not authenticated:
        return JsonResponse({'detail': 'Sign in required'}, status=401)
    try:
        lat, lng = float(request.GET['lat']), float(request.GET['lng'])
        if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise ValueError()
    except (KeyError, ValueError):
        return JsonResponse({'detail': 'Invalid coordinates'}, status=400)
    return JsonResponse(nearby(lat, lng))
