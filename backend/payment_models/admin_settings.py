from sqlalchemy import String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class AdminSettings(Identity, Base):
    __tablename__ = 'pg_admin_settings'
    provider: Mapped[str] = mapped_column(String(20), default='phonepe')
    environment: Mapped[str] = mapped_column(String(12))
    api_version: Mapped[str] = mapped_column(String(2))
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


class PaymentMethod(Base):
    __tablename__ = 'pg_payment_methods'
    name: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    settings_id: Mapped[int | None] = mapped_column(ForeignKey('pg_admin_settings.id'))
