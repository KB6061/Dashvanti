from fastapi import APIRouter, Depends
from fastapi.responses import Response
from backend.db import get_db
from backend.security import role
from backend.services import report_service

router = APIRouter()

def download(data, name):
    return Response(data, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{name}"',
        'Cache-Control': 'private, no-store',
    })

@router.get('/reports/orders/{order_id}/bill')
def bill(order_id: int, tz: str = "America/Chicago", user=Depends(role('customer', 'restaurant')), db=Depends(get_db, scope='function')):
    return download(report_service.bill(db, user, order_id, tz), f'dashvanti-order-{order_id}.pdf')

@router.get('/reports/earnings')
def earnings(period: str = 'monthly', tz: str = 'America/Chicago', user=Depends(role('driver')), db=Depends(get_db, scope='function')):
    return download(report_service.earnings(db, user, period, tz), f'dashvanti-earnings-{period}.pdf')
