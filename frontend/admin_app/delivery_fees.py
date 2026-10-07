import json
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from .views import admin_api, admin_required


@admin_required
@require_http_methods(['GET', 'POST'])
def manage(request):
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            code = request.POST.get('country_code', '').strip().upper()
            if action == 'country':
                payload = {key: request.POST.get(key, '').strip() for key in ('country_name', 'currency_code', 'currency_symbol', 'distance_unit')}
                payload.update(country_code=code, is_active=request.POST.get('active') == 'on')
                payload.update(minimum_service_percent=request.POST.get('minimum_service_percent', '0'), maximum_service_percent=request.POST.get('maximum_service_percent', '100'))
                admin_api('PUT', '/admin/delivery-fees/countries', payload)
            elif action == 'settings':
                fields = ('state', 'city', 'base_fee', 'small_order_threshold', 'small_order_fee', 'free_delivery_max_distance', 'service_fee_percent')
                payload = {key: request.POST.get(key, '') for key in fields}
                payload.update(free_delivery_threshold=request.POST.get('free_delivery_threshold') or None,
                    distance_tiers=json.loads(request.POST.get('distance_tiers', '[]')), active=request.POST.get('active') == 'on')
                admin_api('PUT', f'/admin/delivery-fees/settings/{code}', payload)
            elif action == 'surge':
                payload = {key: request.POST.get(key, '') for key in ('state', 'city', 'reason', 'amount')}
                payload.update(active=request.POST.get('active') == 'on', starts_at=request.POST.get('starts_at') or None, ends_at=request.POST.get('ends_at') or None)
                rule_id = request.POST.get('rule_id')
                path = f'/admin/delivery-fees/surges/{code}' + (f'/{int(rule_id)}' if rule_id else '')
                admin_api('PUT' if rule_id else 'POST', path, payload)
            elif action in {'delete-settings', 'delete-surge'}:
                kind = 'settings' if action == 'delete-settings' else 'surges'
                admin_api('DELETE', f'/admin/delivery-fees/{kind}/{int(request.POST["rule_id"])}')
            else:
                raise ValueError('Unknown action')
            messages.success(request, 'Delivery pricing saved. Existing orders retain their original fees.')
            return redirect('/admin/delivery-fees')
        except (RuntimeError, ValueError, KeyError) as exc:
            messages.error(request, str(exc))
    data = admin_api('GET', '/admin/delivery-fees')
    selected = next((row for row in data['settings'] if str(row['id']) == request.GET.get('edit')), {})
    if request.method == 'POST' and request.POST.get('action') == 'settings':
        selected = dict(request.POST.items())
        selected['active'] = request.POST.get('active') == 'on'
        tiers = request.POST.get('distance_tiers', '')
    else:
        tiers = json.dumps(selected.get('distance_tiers', [{'up_to': None, 'fee': '0', 'per_unit': '0'}]), indent=2)
    labels = [('base_fee', 'Base fee'), ('small_order_threshold', 'Small order threshold'),
        ('small_order_fee', 'Small order fee'), ('free_delivery_threshold', 'Free delivery food threshold (blank disables)'),
        ('free_delivery_max_distance', 'Free delivery maximum distance'), ('service_fee_percent', 'Service fee percent')]
    return render(request, 'admin_app/delivery_fees.html', {'data': data, 'selected': selected,
        'tiers': tiers, 'fee_fields': [{'name': key, 'label': label, 'value': selected.get(key, '')} for key, label in labels],
        'reasons': ['rain', 'holiday', 'festival', 'peak_hours', 'high_demand', 'low_driver_availability'],
        'active_nav': 'delivery-fees', 'title': 'Delivery fee management'})
