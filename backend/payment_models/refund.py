from sqlalchemy import String, Text, BigInteger, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class Refund(Identity, Base):
    __tablename__ = 'pg_refunds'
    __table_args__ = (UniqueConstraint('payment_id', 'request_key'),)
    payment_id: Mapped[int] = mapped_column(ForeignKey('pg_payments.id'), index=True)
    merchant_refund_id: Mapped[str] = mapped_column(String(63), unique=True)
    request_key: Mapped[str] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(24), default='REQUESTED')
    provider_refund_id: Mapped[str | None] = mapped_column(String(100))
    checked_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)
