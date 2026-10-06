from datetime import datetime,timezone
from sqlalchemy import ForeignKey, String, Float, DateTime, UniqueConstraint, Integer,Identity
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

class EssentialGPSPoint(Base):
    __tablename__ = 'essential_gps_points'
    __table_args__ = (UniqueConstraint('event_id'),)
    id: Mapped[int] = mapped_column(Integer,Identity(),primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64))
    driver_id: Mapped[int] = mapped_column(ForeignKey('drivers.id', ondelete='CASCADE'), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime,default=lambda:datetime.now(timezone.utc).replace(tzinfo=None))
