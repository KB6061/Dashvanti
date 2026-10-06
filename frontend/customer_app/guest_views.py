from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from common_app.api import api_client
from django.conf import settings
import httpx


@require_http_methods(['GET'])
def guest_browse(request):
    if request.session.get('token') and request.session.get('role') == 'customer':
        return redirect('/customer/dashboard')
    query = request.GET.get('q', '').strip()[:120]
    try:
        response = api_client().get(settings.API_URL + '/restaurants', params={'q': query, 'page_size': 100}, headers={'Cookie': ''})
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return render(request, 'error.html', {'error': 'Restaurants are temporarily unavailable. Please try again.'}, status=503)
    response = render(request, 'customer_app/guest.html', {
        'restaurants': data.get('items', []) if isinstance(data, dict) else data,
        'query': query,
    })
    response['Cache-Control'] = 'no-store'
    return response
