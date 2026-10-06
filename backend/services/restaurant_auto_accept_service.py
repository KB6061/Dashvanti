from sqlalchemy import select
from backend.models import Order, User


def accept_order(db, order):
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update().execution_options(populate_existing=True))
    if not order or order.status != 'PLACED': return False
    if order.payment_mode == 'PhonePe':
        from backend.payment_models import Payment, PaymentOrder
        paid = db.scalar(select(Payment.id).join(PaymentOrder, PaymentOrder.payment_id == Payment.id).where(
            PaymentOrder.order_id == order.id, Payment.status == 'COMPLETED', Payment.environment == 'production'))
        if not paid: return False
    restaurant = db.get(User, order.restaurant_id)
    if not restaurant or restaurant.role != 'restaurant': return False
    from backend.services.delivery_service import transition
    transition(db, restaurant, order.id, 'ACCEPTED')
    from backend.services.operations_service import audit
    audit(db, None, 'order-auto-accepted', f'order:{order.id}', 'Restaurant automatically accepted the order; delivery requires driver acceptance.')
    return True


def accept_pending(db):
    rows = list(db.scalars(select(Order).where(Order.status == 'PLACED').order_by(Order.id).limit(100).with_for_update(skip_locked=True)))
    for order in rows: accept_order(db, order)
