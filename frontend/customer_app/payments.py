import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from common_app.api import call, APIError
from common_app.views import protected


@protected
@require_http_methods(['GET', 'POST'])
def proxy(request, action):
    paths = {'methods': ('GET', '/payment/methods'), 'pay': ('POST', '/phonepe/pay'),
        'status': ('POST', '/phonepe/status'), 'country': ('PUT', '/payment/country')}
    method, path = paths[action]
    if request.method != ('GET' if method == 'GET' else 'POST'):
        return JsonResponse({'detail': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body) if request.method == 'POST' else None
        result = call(request, method, path, data)
        return JsonResponse(result, headers={'Cache-Control': 'no-store'})
    except (ValueError, TypeError):
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)


@protected
@require_http_methods(['GET'])
def result(request, transaction_id):
    payment = call(request, 'GET', f'/phonepe/transaction/{transaction_id}')
    return render(request, 'customer_app/payment_result.html', {'payment': payment, 'title': 'Payment status'})
