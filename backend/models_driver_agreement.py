from datetime import datetime
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class DriverAgreementAcceptance(Identity, Base):
    __tablename__ = 'driver_agreement_acceptance'
    driver_temp_id: Mapped[str] = mapped_column(String(36), unique=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey('drivers.id', ondelete='SET NULL'), index=True)
    agreement_version: Mapped[str] = mapped_column(String(40), index=True)
    agreement_hash: Mapped[str] = mapped_column(String(64))
    agreement_content: Mapped[str] = mapped_column(Text)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    full_legal_name: Mapped[str] = mapped_column(String(160), default='')
    accepted: Mapped[bool] = mapped_column(default=False)
    accepted_at: Mapped[datetime | None]
    acceptance_timestamp: Mapped[datetime | None]
    ip_address: Mapped[str] = mapped_column(String(45), default='')
    device_information: Mapped[str] = mapped_column(Text, default='')
    browser_information: Mapped[str] = mapped_column(Text, default='')
    acknowledgements: Mapped[str] = mapped_column(Text, default='[]')
    scroll_completed_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
    registered_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=now)
