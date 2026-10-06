from datetime import datetime,timezone
from sqlalchemy import ForeignKey,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from backend.db import Base

class DriverUpcomingOrder(Base):
    __tablename__='driver_upcoming_orders'
    driver_id: Mapped[int]=mapped_column(ForeignKey('drivers.id',ondelete='CASCADE'),primary_key=True)
    order_id: Mapped[int]=mapped_column(ForeignKey('orders.id',ondelete='CASCADE'),unique=True,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
