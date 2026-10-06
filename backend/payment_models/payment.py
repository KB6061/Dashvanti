from sqlalchemy import String, Text, Integer, BigInteger, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class Payment(Identity, Base):
    __tablename__ = 'pg_payments'
    merchant_order_id: Mapped[str] = mapped_column(String(63), unique=True)
    provider: Mapped[str] = mapped_column(String(20), default='phonepe')
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    settings_id: Mapped[int] = mapped_column(ForeignKey('pg_admin_settings.id'))
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    country: Mapped[str] = mapped_column(String(2))
    environment: Mapped[str] = mapped_column(String(12), default='sandbox')
    api_version: Mapped[str] = mapped_column(String(2), default='v2')
    status: Mapped[str] = mapped_column(String(24), default='INITIATING', index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(100))
    redirect_url: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[int | None] = mapped_column(BigInteger)
    checked_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)
    updated_at: Mapped[object] = mapped_column(DateTime, default=now, onupdate=now)


class PaymentOrder(Identity, Base):
    __tablename__ = 'pg_payment_orders'
    payment_id: Mapped[int] = mapped_column(ForeignKey('pg_payments.id', ondelete='CASCADE'), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id', ondelete='SET NULL'), unique=True)
    original_order_id: Mapped[int] = mapped_column(Integer)


class PaymentEvent(Identity, Base):
    __tablename__ = 'pg_payment_events'
    payment_id: Mapped[int | None] = mapped_column(ForeignKey('pg_payments.id', ondelete='SET NULL'), index=True)
    event: Mapped[str] = mapped_column(String(80))
    dedup_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    details: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


class Settlement(Identity, Base):
    __tablename__ = 'pg_settlements'
    reference: Mapped[str] = mapped_column(String(120), unique=True)
    provider: Mapped[str] = mapped_column(String(20), default='phonepe')
    environment: Mapped[str] = mapped_column(String(12))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    status: Mapped[str] = mapped_column(String(24))
    settled_at: Mapped[object | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(40), default='merchant_report')
