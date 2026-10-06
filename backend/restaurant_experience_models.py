from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

class RestaurantPlan(Base):
    __tablename__ = 'customer_restaurant_plans'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id', ondelete='CASCADE'), primary_key=True)
    scheduled_for: Mapped[datetime | None]

class ScheduledOrder(Base):
    __tablename__ = 'scheduled_orders'
    __table_args__ = (Index('ix_scheduled_orders_due', 'released', 'release_at'),)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True)
    release_at: Mapped[datetime] = mapped_column(index=True)
    released: Mapped[bool] = mapped_column(default=False)

class GroupOrder(Base):
    __tablename__ = 'customer_group_orders'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id', ondelete='CASCADE'))
    host_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'))
    invite_code: Mapped[str] = mapped_column(String(32), unique=True)
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default='OPEN')

class GroupMember(Base):
    __tablename__ = 'customer_group_members'
    group_id: Mapped[str] = mapped_column(ForeignKey('customer_group_orders.id', ondelete='CASCADE'), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True, index=True)

class GroupItem(Base):
    __tablename__ = 'customer_group_items'
    __table_args__ = (UniqueConstraint('group_id', 'customer_id', 'menu_item_id'),)
    group_id: Mapped[str] = mapped_column(ForeignKey('customer_group_orders.id', ondelete='CASCADE'), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id', ondelete='CASCADE'), primary_key=True)
    quantity: Mapped[int]
