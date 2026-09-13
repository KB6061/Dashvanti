from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.schemas import DriverReassignment
from backend.schemas import (
    AdminUserCreate, AdminUserUpdate, BannerInput, MessageInput, PresentationInput, PromotionInput, TicketInput, TicketUpdate,
)
from backend.security import admin_secret, current_user, role
from backend.services import operations_service

router = APIRouter()

@router.get('/content/home')
def home(db=Depends(get_db, scope='function')):
    return operations_service.home(db)

@router.get('/content/restaurant')
def restaurant_content(user=Depends(role('restaurant')), db=Depends(get_db, scope='function')):
    return operations_service.presentation(db, user)

@router.put('/content/restaurant')
def save_restaurant_content(data: PresentationInput, user=Depends(role('restaurant')), db=Depends(get_db, scope='function')):
    return operations_service.save_presentation(db, user, data)

@router.get('/content/promotions')
def promotions(db=Depends(get_db, scope='function')):
    return operations_service.list_promotions(db)

@router.put('/content/banner')
def save_banner(data: BannerInput, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.save_banner(db, data)

@router.post('/content/promotions', status_code=201)
def create_promotion(data: PromotionInput, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.save_promotion(db, data)

@router.put('/content/promotions/{promotion_id}')
def update_promotion(promotion_id: int, data: PromotionInput, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.save_promotion(db, data, promotion_id)

@router.delete('/content/promotions/{promotion_id}')
def remove_promotion(promotion_id: int, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.delete_promotion(db, promotion_id)

@router.get('/operations/tickets')
def user_tickets(user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.tickets(db, user)

@router.post('/operations/tickets', status_code=201)
def create_ticket(data: TicketInput, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.create_ticket(db, user, data)

@router.get('/operations/tickets/all')
def admin_tickets(_=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.all_tickets(db)

@router.put('/operations/tickets/{ticket_id}')
def resolve_ticket(ticket_id: int, data: TicketUpdate, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.update_ticket(db, ticket_id, data)

@router.get('/operations/orders/{order_id}/messages')
def order_messages(order_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.messages(db, user, order_id)

@router.post('/operations/orders/{order_id}/messages', status_code=201)
def create_order_message(order_id: int, data: MessageInput, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.send_message(db, user, order_id, data)

@router.get('/operations/notifications')
def user_notifications(user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.notifications(db, user)

@router.post('/operations/notifications/{notification_id}/read')
def read_notification(notification_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return operations_service.mark_notification(db, user, notification_id)

@router.get('/operations/audit')
def audit(_=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.audit_events(db)


@router.get('/operations/admin/users')
def admin_users(q: str = '', role_name: str = '', status: str = '', _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.admin_users(db, q, role_name, status)

@router.post('/operations/admin/users', status_code=201)
def admin_create_user(data: AdminUserCreate, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.admin_create_user(db, data)

@router.put('/operations/admin/users/{user_id}')
def admin_update_user(user_id: int, data: AdminUserUpdate, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.admin_update_user(db, user_id, data)

@router.delete('/operations/admin/users/{user_id}')
def admin_delete_user(user_id: int, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    return operations_service.admin_delete_user(db, user_id)


@router.get('/operations/orders/{order_id}/nearby-drivers')
def nearby_order_drivers(order_id: int, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    from backend.models import Order
    from backend.services.dispatch_service import nearby
    from fastapi import HTTPException
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, 'Order not found')
    return nearby(db, order)

@router.post('/operations/orders/{order_id}/reassign')
def reassign_order(order_id: int, data: DriverReassignment, _=Depends(admin_secret), db=Depends(get_db, scope='function')):
    from backend.services.dispatch_service import reassign
    return reassign(db, order_id, data.driver_id, data.expected_driver_id, data.reason)
