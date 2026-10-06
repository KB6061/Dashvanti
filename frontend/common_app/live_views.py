from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .api import call, APIError


@require_GET
def order_statuses(request, portal):
    if portal not in {'customer', 'driver', 'restaurant', 'admin'}:
        return JsonResponse({'detail': 'Unknown portal'}, status=404)
    authorized = request.session.get('admin_authenticated') if portal == 'admin' else (
        request.session.get('token') and request.session.get('role') == portal
    )
    if not authorized:
        return JsonResponse({'detail': 'Sign in required'}, status=401)
    try:
        ids = {int(value) for value in request.GET.get('ids', '').split(',') if value}
        if len(ids) > 500 or any(value <= 0 for value in ids):
            raise ValueError()
    except ValueError:
        return JsonResponse({'detail': 'Invalid order IDs'}, status=400)
    if not ids:
        rows = []
    elif portal == 'admin':
        from backend.db import Session
        from backend.models import Order
        from sqlalchemy import select
        with Session() as db:
            rows = [dict(row._mapping) for row in db.execute(
                select(Order.id, Order.status, Order.driver_id).where(Order.id.in_(ids))
            )]
    else:
        try:
            rows = [{'id': row['id'], 'status': row['status'], 'driver_id': row.get('driver_id')}
                    for row in call(request, 'GET', '/orders') if row['id'] in ids]
        except (APIError, RuntimeError):
            return JsonResponse({'detail': 'Live status temporarily unavailable'}, status=503)
    return JsonResponse(rows, safe=False, headers={'Cache-Control': 'private, no-store'})
