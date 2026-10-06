from sqlalchemy import select
from backend.db import Session
from backend.payment_models import Payment, Refund
from backend.services.phonepe_service import reconcile


def main():
    with Session() as db:
        payments = list(db.scalars(select(Payment.id).where(Payment.status.in_(['PENDING', 'UNKNOWN', 'INITIATING'])).order_by(Payment.checked_at.asc().nullsfirst(), Payment.id).limit(20)))
        refunds = list(db.execute(select(Refund.payment_id, Refund.id).where(Refund.status.in_(['PENDING', 'UNKNOWN', 'REQUESTED'])).order_by(Refund.checked_at.asc().nullsfirst(), Refund.id).limit(20)))
    for payment_id in payments:
        reconcile(payment_id)
    for payment_id, refund_id in refunds:
        reconcile(payment_id, refund_id)


if __name__ == '__main__':
    main()
