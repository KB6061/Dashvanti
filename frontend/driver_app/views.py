from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from common_app.api import call
from common_app.views import protected, orders, order, stats
from driver_app.forms import AvailabilityForm

DRIVER_ACTIONS = {
    'READY_FOR_PICKUP': [('ON_THE_WAY_TO_RESTAURANT', 'Start Journey')],
    'DRIVER_ASSIGNED': [('ON_THE_WAY_TO_RESTAURANT', 'Start Journey')],
    'ON_THE_WAY_TO_RESTAURANT': [('ARRIVED_AT_RESTAURANT', 'Arrived at Restaurant')],
    'ARRIVED_AT_RESTAURANT': [('PICKED_UP', 'Picked up order')],
    'PICKED_UP': [('ON_THE_WAY_TO_CUSTOMER', 'Out for Delivery')],
    'ON_THE_WAY_TO_CUSTOMER': [('DELIVERED', 'Delivered')],
}

@protected
@require_http_methods(['GET','POST'])
def dashboard(request):
    if request.method == 'POST' and request.POST.get('dashboard_action') == 'location':
        result = call(request,'POST','/driver/location/update',{
            'latitude': request.POST.get('latitude'),
            'longitude': request.POST.get('longitude'),
            'heading': request.POST.get('heading') or None,
        })
        return JsonResponse(result)
    me = call(request,'GET','/me')
    profile = me['driver']
    form = AvailabilityForm(request.POST or None,initial=profile)
    if request.method=='POST' and form.is_valid():
        call(request,'PUT','/driver/profile',form.cleaned_data)
        return redirect(request.path)
    available = call(request,'GET','/delivery/available')
    driver_orders = call(request,'GET','/orders')
    active_orders = []
    completed_orders = []
    for row in driver_orders:
        row = dict(row)
        action_status = row.get('status')
        if action_status not in {'DELIVERED','REJECTED','CANCELLED','CANCELED'}:
            activity = call(request,'GET',f"/order/{row['id']}/tracking")
            action_status = activity['driver_status']
            if action_status == 'ARRIVED_AT_RESTAURANT' and activity['restaurant_status'] != 'READY_FOR_PICKUP':
                action_status = None
        row['actions'] = DRIVER_ACTIONS.get(action_status, [])
        if row.get('status') == 'DELIVERED':
            completed_orders.append(row)
        elif row.get('status') not in {'REJECTED','CANCELLED','CANCELED'}:
            active_orders.append(row)
    stats_data = call(request,'GET','/stats',params={'period':'daily'})
    weekly = [92, 124, 84, 112, 146, 176, 118, 151]
    map_markers = []
    for row in active_orders + available:
        if row.get('restaurant_address'):
            map_markers.append({'id': f"pickup-{row['id']}", 'name': f"Pickup: {row.get('restaurant_name', 'Restaurant')}", 'address': row['restaurant_address']})
        if row.get('address') and row['address'] != 'Pickup at restaurant':
            map_markers.append({'id': f"dropoff-{row['id']}", 'name': f"Drop-off: Order #{row['id']}", 'address': row['address']})
    context = {
        'form': form,
        'me': me,
        'profile': profile,
        'available': available,
        'map_markers': map_markers,
        'active_orders': active_orders[:3],
        'completed_orders': completed_orders[:4],
        'stats': stats_data,
        'weekly': weekly,
        'rating': '4.8',
        'title':'Driver dashboard',
    }
    return render(request,'driver_app/dashboard.html',context)

@protected
@require_http_methods(['POST'])
def accept(request,order_id):
    call(request,'POST',f'/delivery/{order_id}/accept')
    return redirect(f'/driver/order/{order_id}')

@protected
@require_http_methods(['POST'])
def navigation_update(request, kind):
    import json
    from common_app.api import APIError
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict):
            raise ValueError()
        return JsonResponse(call(request,'POST',f'/driver/{kind}/update',data),headers={'Cache-Control':'no-store'})
    except APIError as exc:
        return JsonResponse({'detail':str(exc)},status=exc.status)
    except (ValueError,TypeError):
        return JsonResponse({'detail':'Invalid navigation request'},status=400)

@protected
@require_http_methods(['GET', 'POST'])
def presence(request):
    import json
    from common_app.api import APIError
    try:
        data = json.loads(request.body) if request.method == 'POST' else None
        return JsonResponse(call(request, request.method, '/driver/presence', data),
                            headers={'Cache-Control': 'no-store'})
    except (ValueError, TypeError):
        return JsonResponse({'detail': 'Invalid availability request'}, status=400)
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)
