from django.conf import settings
from common_app.api import APIError, call

def restaurant_notifications(request, role, signed_in):
    if role != 'restaurant' or not signed_in:
        return []
    try:
        orders = call(request,'GET','/orders')
        pending = [row for row in orders if row.get('status') == 'PLACED']
        request.restaurant_notification_count = len(pending)
        return pending[:5]
    except APIError:
        request.restaurant_notification_count = 'error'
        return []

def portal(request):
    parts = request.path.strip('/').split('/')
    role = parts[0]
    public_home = request.path == '/'
    public_auth = role in {'customer','restaurant','driver'} and len(parts) > 1 and parts[1] in {'login','register','forgot','reset'}
    signed_in = bool(request.session.get('token')) and not public_home and not public_auth
    return {
        'portal': role,
        'public_home': public_home,
        'signed_in': signed_in,
        'session_name': request.session.get('name', ''),
        'session_email': request.session.get('email', ''),
        'session_profile_photo': request.session.get('profile_photo'),
        'portal_urls': settings.PORTAL_URLS,
        'driver_secure_url': 'https://' + request.get_host().split(':')[0] + ':8443/driver/dashboard',
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'restaurant_notifications': restaurant_notifications(request, role, signed_in),
    }
