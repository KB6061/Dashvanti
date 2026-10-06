from sqlalchemy import Integer, BigInteger, JSON, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base


class OrderBroadcastEvent(Base):
    __tablename__ = 'order_broadcast_events'
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('orders.id', ondelete='CASCADE', name='fk_order_broadcast_order'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
