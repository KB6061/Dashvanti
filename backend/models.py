from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Text, Numeric, ForeignKey, UniqueConstraint, Integer, Float, DateTime, Identity as SQLIdentity
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Identity:
    id: Mapped[int] = mapped_column(Integer, SQLIdentity(), primary_key=True)

class User(Identity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), nullable=True, default='')
    token_version: Mapped[int] = mapped_column(default=0)
    order_sound_enabled: Mapped[bool] = mapped_column(default=False)

class Customer(Base):
    __tablename__ = 'customers'
    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    order_mode: Mapped[str] = mapped_column(String(20), default='delivery')

class CustomerLocation(Base):
    __tablename__ = 'customer_locations'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

class Restaurant(Base):
    __tablename__ = 'restaurants'
    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), nullable=True, default='')
    cuisine: Mapped[str] = mapped_column(String(80), default='Indian')
    kind: Mapped[str] = mapped_column(String(20), default='restaurant')
    address: Mapped[str] = mapped_column(String(500), nullable=True, default='')
    is_open: Mapped[bool] = mapped_column(default=False)
    opening: Mapped[str] = mapped_column(String(5), default='09:00')
    closing: Mapped[str] = mapped_column(String(5), default='22:00')
    delivery_minutes: Mapped[int] = mapped_column(default=30)

class Driver(Base):
    __tablename__ = 'drivers'
    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    online: Mapped[bool] = mapped_column('is_online', default=False)
    vehicle_type: Mapped[str] = mapped_column(String(80), nullable=True, default='')
    vehicle_number: Mapped[str] = mapped_column(String(80), nullable=True, default='')

class DriverLocation(Base):
    __tablename__ = 'driver_locations'
    driver_id: Mapped[int] = mapped_column(ForeignKey('drivers.id'), primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=now)

class Address(Identity, Base):
    __tablename__ = 'addresses'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    label: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(default=False)
    place_id: Mapped[str | None] = mapped_column(String(255))

class MenuItem(Identity, Base):
    __tablename__ = 'menu_items'
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000), nullable=True, default='')
    category: Mapped[str] = mapped_column(String(80), nullable=True, default='General')
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    veg: Mapped[bool] = mapped_column(default=True)
    available: Mapped[bool] = mapped_column(default=True)

class CartItem(Identity, Base):
    __tablename__ = 'cart_items'
    __table_args__ = (UniqueConstraint('customer_id', 'menu_item_id'),)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id'))
    special_instructions: Mapped[str | None] = mapped_column(String(1000))
    quantity: Mapped[int]

class Order(Identity, Base):
    __tablename__ = 'orders'
    __table_args__ = (UniqueConstraint('customer_id', 'request_key'),)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id'), index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey('drivers.id'), index=True)
    request_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default='PLACED')
    mode: Mapped[str] = mapped_column(String(20))
    payment_mode: Mapped[str] = mapped_column(String(40), default='Card')
    address: Mapped[str] = mapped_column(String(500))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tip: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    service_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    customer_zip: Mapped[str | None] = mapped_column(String(10))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    item_tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    delivery_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    platform_tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(default=now)

class OrderItem(Identity, Base):
    __tablename__ = 'order_items'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id'))
    name: Mapped[str] = mapped_column(String(120))
    special_instructions: Mapped[str | None] = mapped_column(String(1000))
    quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class PayoutTransaction(Identity, Base):
    __tablename__ = 'payout_transactions'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    payee_role: Mapped[str] = mapped_column(String(20), index=True)
    payee_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default='PENDING', index=True)
    method: Mapped[str] = mapped_column(String(30), default='QUICK_PAY')
    reference: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class DeliveryStatus(Identity, Base):
    __tablename__ = 'delivery_status'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    status: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(default=now)

class File(Identity, Base):
    __tablename__ = 'files'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    purpose: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int | None]
    path: Mapped[str] = mapped_column(String(1000))
    mime: Mapped[str] = mapped_column(String(80))

class Rating(Identity, Base):
    __tablename__ = 'ratings'
    __table_args__ = (UniqueConstraint('order_id'),)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'))
    restaurant: Mapped[int]
    driver: Mapped[int | None]

class Review(Identity, Base):
    __tablename__ = 'reviews'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    text: Mapped[str] = mapped_column(String(2000))

class SystemConfig(Base):
    __tablename__ = 'system_config'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))

class PasswordReset(Identity, Base):
    __tablename__ = 'password_resets'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used: Mapped[bool] = mapped_column(default=False)

class Outbox(Identity, Base):
    __tablename__ = 'event_outbox'
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)




class RestaurantPresentation(Base):
    __tablename__ = 'restaurant_presentations'
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id'), primary_key=True)
    cover_file_id: Mapped[int | None] = mapped_column(ForeignKey('files.id'), nullable=True)
    logo_file_id: Mapped[int | None] = mapped_column(ForeignKey('files.id'), nullable=True)
    gallery_file_ids: Mapped[str] = mapped_column(Text, default='[]')
    busy_mode: Mapped[str] = mapped_column(String(20), default='open')
    busy_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prep_extra_minutes: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class PlatformContent(Base):
    __tablename__ = 'platform_content'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default='')
    description: Mapped[str] = mapped_column(Text, default='')
    enabled: Mapped[bool] = mapped_column(default=False)
    media_file_id: Mapped[int | None] = mapped_column(ForeignKey('files.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class Promotion(Identity, Base):
    __tablename__ = 'promotions'
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default='')
    code: Mapped[str] = mapped_column(String(40), unique=True)
    percent: Mapped[int] = mapped_column(Integer)
    minimum: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cap: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    first_order_only: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class SupportTicket(Identity, Base):
    __tablename__ = 'support_tickets'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='open')
    resolution: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class OrderMessage(Identity, Base):
    __tablename__ = 'order_messages'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Notification(Identity, Base):
    __tablename__ = 'notifications'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class AuditEvent(Identity, Base):
    __tablename__ = 'audit_events'
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(160))
    details: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
