from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base


class CustomerPushDevice(Base):
    __tablename__ = 'customer_push_devices'
    installation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    token_version: Mapped[int] = mapped_column(Integer)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerPushDelivery(Base):
    __tablename__ = 'customer_push_deliveries'
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey('order_broadcast_events.id', ondelete='CASCADE'), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(64), ForeignKey('customer_push_devices.installation_id', ondelete='CASCADE'), primary_key=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
