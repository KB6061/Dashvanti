import json
import uuid
from urllib.parse import urlencode
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.conf import settings
import httpx
from .views import admin_required, admin_api


@admin_required
@require_http_methods(['GET', 'POST'])
def payments(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'settings':
                fields = ('environment', 'api_version', 'merchant_id', 'salt_key', 'api_key', 'client_id', 'client_secret', 'webhook_username', 'webhook_password')
                data = {key: request.POST.get(key, '') for key in fields}
                data.update({'salt_index': int(request.POST.get('salt_index', '1')), 'client_version': int(request.POST.get('client_version', '1')), 'confirm_production': request.POST.get('confirm_production') == 'on'})
                admin_api('POST', '/admin/payment/settings/update', data)
            elif action == 'toggle':
                admin_api('POST', '/admin/payment/methods/toggle', {'method': request.POST.get('method'), 'enabled': request.POST.get('enabled') == 'true'})
            elif action == 'currency':
                admin_api('POST', '/admin/payment/restaurant-currency', {'restaurant_id': int(request.POST['restaurant_id']), 'currency': request.POST['currency'], 'confirm_prices': request.POST.get('confirm_prices') == 'on'})
            elif action == 'settlement':
                data = json.loads(request.POST.get('settlement', '{}'))
                admin_api('POST', '/admin/payment/settlements/import', data)
            else:
                raise ValueError('Unknown payment action')
            messages.success(request, 'Payment settings saved')
        except (RuntimeError, ValueError, KeyError, httpx.HTTPError) as exc:
            messages.error(request, str(exc) if not isinstance(exc, httpx.HTTPError) else 'Payment service is unavailable')
        return redirect('/admin/payments')
    try:
        offset = max(0, int(request.GET.get('offset', '0')))
    except ValueError:
        offset = 0
    status = request.GET.get('status', '')[:24]
    query = urlencode({'offset': offset, 'limit': 25, 'status': status})
    data = admin_api('GET', '/admin/payment/transactions?' + query)
    return render(request, 'admin_app/payments.html', {'payment_settings': admin_api('GET', '/admin/payment/settings'),
        'payment_data': data, 'settlement_data': admin_api('GET', '/admin/payment/settlements'),
        'status': status, 'next_offset': offset + 25 if offset + 25 < data['total'] else None,
        'previous_offset': max(0, offset - 25) if offset else None,
        'active_nav': 'payments', 'title': 'Payment management'})


@admin_required
@require_http_methods(['GET', 'POST'])
def transaction(request, transaction_id):
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            if action == 'recheck':
                admin_api('POST', f'/admin/payment/transaction/{transaction_id}/status', {})
            elif action == 'refund':
                admin_api('POST', f'/admin/payment/refund/{transaction_id}', {'amount': int(request.POST['amount']), 'reason': request.POST['reason'], 'request_key': request.POST['request_key']})
            elif action == 'refund_status':
                detail = admin_api('GET', f'/admin/payment/transaction/{transaction_id}')
                refund_id = int(request.POST['refund_id'])
                if not any(row['id'] == refund_id for row in detail['refunds']):
                    raise ValueError('Refund does not belong to this transaction')
                admin_api('POST', f'/admin/payment/refund/{refund_id}/status', {})
            else:
                raise ValueError('Unknown transaction action')
            messages.success(request, 'Payment action completed')
        except (RuntimeError, ValueError, KeyError, httpx.HTTPError) as exc:
            messages.error(request, str(exc) if not isinstance(exc, httpx.HTTPError) else 'Payment service is unavailable')
        return redirect(f'/admin/payments/{transaction_id}')
    return render(request, 'admin_app/payment_transaction.html', {'transaction': admin_api('GET', f'/admin/payment/transaction/{transaction_id}'),
        'refund_request_key': uuid.uuid4().hex, 'active_nav': 'payments', 'title': 'Payment details'})


@admin_required
@require_http_methods(['GET'])
def logs(request):
    with httpx.Client(timeout=60) as client:
        response = client.get(settings.API_URL + '/admin/payment/logs', headers={'X-Dashvanti-Admin-Secret': settings.ADMIN_PASSWORD})
    result = HttpResponse(response.content, content_type='application/json', status=response.status_code)
    result['Cache-Control'] = 'no-store'
    if response.is_success:
        result['Content-Disposition'] = 'attachment; filename="dashvanti-payment-logs.json"'
    return result
