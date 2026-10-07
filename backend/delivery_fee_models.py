from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class Country(Identity, Base):
    __tablename__ = 'countries'
    country_code: Mapped[str] = mapped_column(String(2), unique=True)
    country_name: Mapped[str] = mapped_column(String(100))
    currency_code: Mapped[str] = mapped_column(String(3))
    currency_symbol: Mapped[str] = mapped_column(String(10))
    distance_unit: Mapped[str] = mapped_column(String(5), default='km')
    minimum_service_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    maximum_service_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CountryDeliverySettings(Identity, Base):
    __tablename__ = 'country_delivery_settings'
    __table_args__ = (UniqueConstraint('country_code', 'state', 'city'),)
    country_code: Mapped[str] = mapped_column(ForeignKey('countries.country_code'))
    state: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    currency_code: Mapped[str] = mapped_column(String(3))
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    small_order_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    small_order_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    free_delivery_threshold: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    free_delivery_max_distance: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    service_fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    distance_tiers: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class DeliverySurgeRule(Identity, Base):
    __tablename__ = 'delivery_surge_rules'
    country_code: Mapped[str] = mapped_column(ForeignKey('countries.country_code'), index=True)
    state: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    reason: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)


class OrderDeliveryFeeSnapshot(Base):
    __tablename__ = 'order_delivery_fee_snapshots'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2))
    currency_code: Mapped[str] = mapped_column(String(3))
    currency_symbol: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    distance_unit: Mapped[str] = mapped_column(String(5))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    distance_miles: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    distance_source: Mapped[str] = mapped_column(String(30))
    food_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    base_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    distance_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    service_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    surge_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    small_order_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    delivery_discount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    settings_snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
