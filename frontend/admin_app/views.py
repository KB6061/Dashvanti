from collections import Counter
from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
import httpx
import sys
from sqlalchemy import func, select

project_root = str(settings.BASE_DIR.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.db import Session
from backend.models import Driver, DriverLocation, Order, OrderItem, DeliveryStatus, Restaurant, User


def admin_api(method, path, data=None):
    headers = {'X-Dashvanti-Admin-Secret': settings.ADMIN_PASSWORD}
    with httpx.Client(timeout=20) as client:
        response = client.request(method, settings.API_URL + path, headers=headers, json=data)
    if response.is_error:
        try:
            detail = response.json().get('detail', 'Request failed')
            if isinstance(detail, list):
                detail = '; '.join(item.get('msg', 'Invalid value') for item in detail)
        except ValueError:
            detail = 'Request failed'
        raise RuntimeError(str(detail))
    return response.json()


def admin_required(view):
    def wrapped(request, *args, **kwargs):
        if not request.session.get('admin_authenticated'):
            return redirect('/admin/login')
        return view(request, *args, **kwargs)
    return wrapped


@require_http_methods(['GET', 'POST'])
def login(request):
    error = ''
    if request.method == 'POST':
        if request.POST.get('password') == settings.ADMIN_PASSWORD:
            request.session.cycle_key()
            request.session['admin_authenticated'] = True
            return redirect('/admin/dashboard')
        error = 'Invalid admin password'
    return render(request, 'admin_app/login.html', {'error': error})


@admin_required
def dashboard(request):
    final_statuses = {'DELIVERED', 'REJECTED', 'CANCELLED'}
    with Session() as db:
        all_orders = list(db.scalars(select(Order).order_by(Order.id.desc()).limit(2000)))
        restaurants = list(db.scalars(select(Restaurant).order_by(Restaurant.name).limit(500)))
        users_by_id = {row.id: row for row in db.scalars(select(User))}
        restaurant_names = {row.id: row.name for row in restaurants}
        today_orders = [row for row in all_orders if row.created_at and row.created_at.date() == date.today()]
        counts = Counter(row.restaurant_id for row in all_orders)
        stats = {
            'customers': db.scalar(select(func.count(User.id)).where(User.role == 'customer')) or 0,
            'restaurants': len(restaurants),
            'drivers': db.scalar(select(func.count(Driver.id))) or 0,
            'online_drivers': db.scalar(select(func.count(Driver.id)).where(Driver.online == True)) or 0,
            'orders': db.scalar(select(func.count(Order.id))) or 0,
            'active_orders': sum(row.status not in final_statuses for row in all_orders),
            'revenue': sum((row.total for row in today_orders), 0),
            'registrations': db.scalar(select(func.count(User.id))) or 0,
        }
        recent_orders = [{
            'id': row.id, 'status': row.status, 'total': row.total,
            'restaurant': restaurant_names.get(row.restaurant_id, f'Restaurant #{row.restaurant_id}'),
            'driver': users_by_id.get(row.driver_id).name if row.driver_id and users_by_id.get(row.driver_id) else 'Unassigned',
        } for row in all_orders[:12]]
        top_restaurants = [{
            'id': restaurant.id, 'name': restaurant.name, 'orders': counts[restaurant.id],
        } for restaurant in sorted(restaurants, key=lambda row: counts[row.id], reverse=True)[:6]]
        hourly = Counter(row.created_at.hour for row in today_orders if row.created_at)
        peak = max(hourly.values(), default=1)
        hourly_volume = [{'hour': hour, 'count': hourly[hour], 'height': max(4, round(hourly[hour] * 100 / peak))} for hour in range(24)]
        map_markers = [
            {'id': f'restaurant-{row.id}', 'name': row.name, 'address': row.address, 'type': 'restaurant'}
            for row in restaurants if row.address
        ]
        for location in db.scalars(select(DriverLocation)):
            driver = users_by_id.get(location.driver_id)
            map_markers.append({
                'id': f'driver-{location.driver_id}', 'name': driver.name if driver else f'Driver #{location.driver_id}',
                'latitude': location.latitude, 'longitude': location.longitude, 'type': 'driver',
            })
    return render(request, 'admin_app/dashboard.html', {
        'portal_urls': settings.PORTAL_URLS, 'stats': stats, 'map_markers': map_markers,
        'recent_orders': recent_orders, 'top_restaurants': top_restaurants,
        'hourly_volume': hourly_volume, 'active_nav': 'dashboard', 'title': 'Dashboard',
    })


def _payload(request, role_name, updating=False):
    payload = {
        'email': request.POST.get('email', '').strip(),
        'name': request.POST.get('name', '').strip(),
        'phone': request.POST.get('phone', '').strip(),
    }
    password = request.POST.get('password', '')
    if password or not updating:
        payload['password'] = password
    if not updating:
        payload['role'] = role_name
    if role_name == 'customer':
        payload['order_mode'] = request.POST.get('order_mode', 'delivery')
    elif role_name == 'restaurant':
        payload.update({
            'restaurant_name': request.POST.get('restaurant_name', '').strip(),
            'description': request.POST.get('description', '').strip(),
            'cuisine': request.POST.get('cuisine', '').strip(),
            'kind': request.POST.get('kind', 'restaurant'),
            'address': request.POST.get('address', '').strip(),
            'is_open': request.POST.get('is_open') == 'on',
            'opening': request.POST.get('opening', '09:00'),
            'closing': request.POST.get('closing', '22:00'),
            'delivery_minutes': request.POST.get('delivery_minutes', '30'),
        })
    elif role_name == 'driver':
        payload.update({
            'online': request.POST.get('online') == 'on',
            'vehicle_type': request.POST.get('vehicle_type', '').strip(),
            'vehicle_number': request.POST.get('vehicle_number', '').strip(),
        })
    return payload


def _manage_users(request, role_name):
    if request.method == 'POST':
        action = request.POST.get('action')
        row_role = request.POST.get('role', role_name)
        try:
            if action == 'create':
                admin_api('POST', '/operations/admin/users', _payload(request, row_role))
                messages.success(request, f'{row_role.title()} added permanently')
            elif action == 'update':
                user_id = request.POST.get('user_id', '')
                admin_api('PUT', f'/operations/admin/users/{user_id}', _payload(request, row_role, True))
                messages.success(request, f'{row_role.title()} updated permanently')
            elif action == 'delete':
                user_id = request.POST.get('user_id', '')
                admin_api('DELETE', f'/operations/admin/users/{user_id}')
                messages.success(request, f'{row_role.title()} deleted permanently')
        except RuntimeError as error:
            messages.error(request, str(error))
        query = {'role': role_name or 'all'}
        return redirect(request.path + '?' + urlencode(query))
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    rows = admin_api('GET', '/operations/admin/users?' + urlencode({
        'q': q, 'role_name': role_name, 'status': status,
    }))
    names = {'customer': 'Customers', 'restaurant': 'Restaurants', 'driver': 'Delivery Fleet', '': 'Search Results'}
    return render(request, 'admin_app/manage_users.html', {
        'rows': rows, 'role': role_name, 'q': q, 'status': status,
        'title': names[role_name], 'active_nav': role_name or 'customers',
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def users(request):
    requested = request.GET.get('role')
    role_name = 'customer' if requested is None else ('' if requested == 'all' else requested)
    if role_name not in {'', 'customer', 'restaurant', 'driver'}:
        role_name = 'customer'
    return _manage_users(request, role_name)


@admin_required
@require_http_methods(['GET', 'POST'])
def restaurants(request):
    return _manage_users(request, 'restaurant')


@admin_required
@require_http_methods(['GET', 'POST'])
def drivers(request):
    return _manage_users(request, 'driver')


@admin_required
def orders(request):
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip().lower()
    with Session() as db:
        stmt = select(Order).order_by(Order.id.desc()).limit(500)
        if status:
            stmt = select(Order).where(Order.status == status).order_by(Order.id.desc()).limit(500)
        orders_found = list(db.scalars(stmt))
        users_by_id = {row.id: row for row in db.scalars(select(User))}
        restaurants_by_id = {row.id: row for row in db.scalars(select(Restaurant))}
        rows = []
        for order in orders_found:
            restaurant = restaurants_by_id.get(order.restaurant_id)
            customer = users_by_id.get(order.customer_id)
            driver = users_by_id.get(order.driver_id) if order.driver_id else None
            haystack = f'{order.id} {order.status} {restaurant.name if restaurant else ""} {customer.name if customer else ""} {driver.name if driver else ""}'.lower()
            if q and q not in haystack:
                continue
            rows.append({'order': order, 'restaurant': restaurant, 'customer': customer, 'driver': driver})
    statuses = ['PLACED', 'ACCEPTED', 'PREPARING', 'READY_FOR_PICKUP', 'ON_THE_WAY_TO_RESTAURANT', 'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER', 'DELIVERED', 'REJECTED']
    return render(request, 'admin_app/orders.html', {'rows': rows, 'status': status, 'q': q, 'statuses': statuses, 'title': 'Orders', 'active_nav': 'orders'})


@require_http_methods(['POST'])
def logout(request):
    request.session.flush()
    return redirect('/admin/login')


@admin_required
@require_http_methods(['GET', 'POST'])
def content(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'banner':
            admin_api('PUT', '/content/banner', {
                'title': request.POST.get('title', ''), 'description': request.POST.get('description', ''),
                'enabled': request.POST.get('enabled') == 'on', 'media_file_id': None,
            })
            messages.success(request, 'Home banner saved')
        elif action == 'promotion':
            admin_api('POST', '/content/promotions', {
                'title': request.POST.get('title', ''), 'description': request.POST.get('description', ''),
                'code': request.POST.get('code', ''), 'percent': request.POST.get('percent', 0),
                'minimum': request.POST.get('minimum', 0), 'cap': request.POST.get('cap', 0),
                'first_order_only': request.POST.get('first_order_only') == 'on',
                'enabled': request.POST.get('enabled') == 'on', 'starts_at': None, 'ends_at': None,
            })
            messages.success(request, 'Promotion saved')
        elif action == 'delete-promotion':
            admin_api('DELETE', '/content/promotions/' + request.POST.get('promotion_id', ''))
            messages.success(request, 'Promotion removed')
        return redirect(request.path)
    return render(request, 'admin_app/content.html', {'home': admin_api('GET', '/content/home'), 'title': 'Promotions', 'active_nav': 'promotions'})


@admin_required
@require_http_methods(['GET', 'POST'])
def operations(request):
    if request.method == 'POST':
        admin_api('PUT', '/operations/tickets/' + request.POST.get('ticket_id', ''), {
            'status': request.POST.get('status', 'open'), 'resolution': request.POST.get('resolution', ''),
        })
        messages.success(request, 'Support ticket updated')
        return redirect(request.path)
    return render(request, 'admin_app/operations.html', {
        'tickets': admin_api('GET', '/operations/tickets/all'),
        'audit_events': admin_api('GET', '/operations/audit'),
        'title': 'Settings', 'active_nav': 'settings',
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def funds(request, section='revenue'):
    valid_fund_sections = {'revenue','orders','refunds','drivers','restaurants','commission','quick-pay','pricing'}
    section = section if section in valid_fund_sections else 'revenue'
    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            if action == 'cancellation_policy':
                admin_api('PUT','/operations/cancellation-policy',{'preparation_percent':request.POST.get('preparation_percent'),'review_threshold':request.POST.get('review_threshold')})
                messages.success(request,'Cancellation rules saved for new orders')
            elif action == 'delete_refund':
                admin_api('DELETE', '/operations/funds/refunds/' + request.POST.get('refund_id',''))
                messages.success(request, 'Pending refund cancelled')
            elif action == 'edit_refund':
                admin_api('PUT', '/operations/funds/refunds/' + request.POST.get('refund_id',''), {
                    'order_id': request.POST.get('order_id'), 'amount': request.POST.get('amount'),
                    'reason': request.POST.get('reason'),
                })
                messages.success(request, 'Pending refund updated')
            elif action == 'refund':
                admin_api('POST', '/operations/funds/refunds', {
                    'order_id': request.POST.get('order_id'), 'amount': request.POST.get('amount'),
                    'reason': request.POST.get('reason'),
                })
                messages.success(request, 'Refund request saved. Transfer is pending payment-provider processing.')
            elif action == 'quick_pay':
                result = admin_api('POST', '/operations/funds/quick-pay', {
                    'order_id': request.POST.get('order_id'),
                    'payee_role': request.POST.get('payee_role'),
                })
                messages.success(request, f"Quick-pay completed: {result['reference']}")
            elif action == 'delete':
                admin_api('DELETE', '/operations/funds/rules/' + request.POST.get('kind', ''))
                messages.success(request, 'Rule deleted')
            else:
                admin_api('PUT', '/operations/funds/rules/' + request.POST.get('kind', ''), {
                    'method': request.POST.get('method'), 'value': request.POST.get('value'),
                    'minimum': request.POST.get('minimum') or '0', 'enabled': request.POST.get('enabled') == 'on',
                })
                messages.success(request, 'Pricing saved')
        except (RuntimeError, httpx.HTTPError) as exc:
            messages.error(request, str(exc))
        return redirect('/admin/funds/' + section)
    from django.core.paginator import Paginator
    from backend.services import revenue_service
    data = admin_api('GET', '/operations/funds')
    data['cancellation_policy'] = admin_api('GET','/operations/cancellation-policy')
    revenue_params = {key: request.GET.get(key, '').strip() for key in ('date_range','start_date','end_date','restaurant_id','driver_id','payment_mode','status','q')}
    revenue = admin_api('GET', '/operations/funds/revenue?' + urlencode(revenue_params))
    if request.GET.get('export') == 'csv':
        response = HttpResponse(revenue_service.export_csv(revenue['rows']), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=admin-revenue.csv'
        return response
    if request.GET.get('export') == 'pdf':
        response = HttpResponse(revenue_service.export_pdf(revenue['rows']), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=admin-revenue.pdf'
        return response
    revenue_size = request.GET.get('revenue_size', '25')
    revenue_size = int(revenue_size) if revenue_size in {'25', '50', '100'} else 25
    revenue_page = Paginator(revenue['rows'], revenue_size).get_page(request.GET.get('revenue_page'))
    revenue['paged_rows'] = revenue_page.object_list
    revenue['page'] = revenue_page
    revenue['total_rows'] = len(revenue['rows'])
    export_params = revenue_params.copy()
    data['export_query'] = urlencode(export_params)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    rows = data['refunds']
    statuses = sorted({row['status'] for row in rows})
    if status:
        rows = [row for row in rows if row['status'] == status]
    if query:
        rows = [row for row in rows if query.casefold() in (str(row['order_id']) + ' ' + row.get('reason', '')).casefold()]
    size = request.GET.get('size', '25')
    size = int(size) if size in {'25', '50', '100'} else 25
    page = Paginator(rows, size).get_page(request.GET.get('page'))
    data.update(revenue=revenue, revenue_filters=revenue_params, refunds=page.object_list, refund_page=page, refund_total=len(rows), refund_query=query, refund_status=status, refund_statuses=statuses, page_size=size, fund_section=section, fund_base='/admin/funds/' + section)
    return render(request, 'admin_app/funds.html', dict(data, title='Fund Management', active_nav='funds'))


@admin_required
@require_http_methods(['GET', 'POST'])
def order_detail(request, order_id):
    if request.method == 'POST':
        try:
            admin_api('POST', f'/operations/orders/{order_id}/reassign', {
                'driver_id': request.POST.get('driver_id'),
                'expected_driver_id': request.POST.get('expected_driver_id') or None,
                'reason': request.POST.get('reason', '').strip(),
            })
            messages.success(request, 'Driver reassigned and notifications sent.')
            return redirect(f'/admin/order/{order_id}')
        except RuntimeError as exc:
            messages.error(request, str(exc))
    with Session() as db:
        order = db.get(Order, order_id)
        if not order:
            raise Http404('Order not found')
        context = {
            'order': order, 'restaurant': db.get(Restaurant, order.restaurant_id),
            'customer': db.get(User, order.customer_id),
            'driver': db.get(User, order.driver_id) if order.driver_id else None,
            'items': list(db.scalars(select(OrderItem).where(OrderItem.order_id == order_id))),
            'history': list(db.scalars(select(DeliveryStatus).where(DeliveryStatus.order_id == order_id).order_by(DeliveryStatus.created_at))),
            'active_nav': 'orders',
        }
        context['can_reassign'] = order.mode == 'delivery' and order.status in {'ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP','ON_THE_WAY_TO_RESTAURANT'}
        if context['can_reassign']:
            try:
                context['nearby_drivers'] = admin_api('GET', f'/operations/orders/{order_id}/nearby-drivers')
            except RuntimeError:
                context['nearby_drivers'] = []
        return render(request, 'admin_app/order_detail.html', context)

@admin_required
@require_http_methods(['GET','POST'])
def cancellation(request, order_id):
    try:
        if request.method=='POST':
            import json
            result=admin_api('POST',f'/operations/orders/{order_id}/cancellation',json.loads(request.body))
        else:
            result=admin_api('GET',f'/operations/orders/{order_id}/cancellation')
        return JsonResponse(result)
    except (RuntimeError,ValueError) as exc:
        return JsonResponse({'detail':str(exc)},status=400)
