from fastapi import APIRouter, Depends, Response
from backend.db import get_db
from backend.security import current_user, role
from backend.schemas import DriverStatusUpdate, Transition
from backend.services import tracking_service, delivery_service

router = APIRouter()

@router.get('/order/{order_id}/tracking')
def tracking(order_id: int, response: Response, user=Depends(current_user), db=Depends(get_db, scope='function')):
    response.headers['Cache-Control'] = 'no-store'
    return tracking_service.tracking(db, user, order_id)

@router.get('/order/{order_id}/restaurant/status')
def restaurant_status(order_id: int, response: Response, user=Depends(current_user), db=Depends(get_db, scope='function')):
    response.headers['Cache-Control'] = 'no-store'
    data = tracking_service.tracking(db, user, order_id)
    return {'order_id': order_id, 'status': data['restaurant_status']}

@router.post('/driver/status/update')
def driver_status(data: DriverStatusUpdate, user=Depends(role('driver')), db=Depends(get_db, scope='function')):
    delivery_service.transition(db, user, data.order_id, data.status)
    return tracking_service.tracking(db, user, data.order_id)

@router.post('/order/{order_id}/restaurant/status')
def update_restaurant_status(order_id: int, data: Transition, user=Depends(role('restaurant')), db=Depends(get_db, scope='function')):
    delivery_service.transition(db, user, order_id, data.status)
    return tracking_service.tracking(db, user, order_id)
