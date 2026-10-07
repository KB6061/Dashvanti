from datetime import datetime
from decimal import Decimal
from sqlalchemy import ForeignKey, String, Text, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class Incident(Base):
    __tablename__ = 'support_incidents'
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id', ondelete='CASCADE'), primary_key=True)
    category: Mapped[str] = mapped_column(String(120), default='General')
    subcategory: Mapped[str] = mapped_column(String(120), default='')
    priority: Mapped[str] = mapped_column(String(12), default='Medium')
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    department: Mapped[str] = mapped_column(String(80), default='Support')
    sla_due_at: Mapped[datetime | None]
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey('support_tickets.id', ondelete='SET NULL'))


class IncidentMessage(Identity, Base):
    __tablename__ = 'support_incident_messages'
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    author_role: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=now)


class IncidentAttachment(Identity, Base):
    __tablename__ = 'support_incident_attachments'
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    internal: Mapped[bool] = mapped_column(default=False)
    path: Mapped[str] = mapped_column(String(1000))
    name: Mapped[str] = mapped_column(String(160))
    mime: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(default=now)


class IncidentEvent(Identity, Base):
    __tablename__ = 'support_incident_events'
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(default=now)


class MenuFavorite(Base):
    __tablename__ = 'customer_menu_favorites'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey('menu_items.id', ondelete='CASCADE'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=now)


class ReviewPublication(Base):
    __tablename__ = 'review_publications'
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id', ondelete='CASCADE'), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default='')
    status: Mapped[str] = mapped_column(String(12), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
    moderated_at: Mapped[datetime | None]
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))


class ReviewHelpful(Base):
    __tablename__ = 'review_helpful_votes'
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)


class ReviewReport(Base):
    __tablename__ = 'review_reports'
    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=now)


class EntityVerification(Base):
    __tablename__ = 'entity_verifications'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    verified: Mapped[bool] = mapped_column(default=False)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    reason: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(default=now)


class GatewayControl(Base):
    __tablename__ = 'account_gateway_controls'
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    countries: Mapped[str] = mapped_column(String(200), default='US,IN')
    updated_at: Mapped[datetime] = mapped_column(default=now)


class PromotionRegion(Base):
    __tablename__ = 'promotion_regions'
    promotion_id: Mapped[int] = mapped_column(ForeignKey('promotions.id', ondelete='CASCADE'), primary_key=True)
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str] = mapped_column(String(100), default='')


class RestaurantRegion(Base):
    __tablename__ = 'restaurant_regions'
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id', ondelete='CASCADE'), primary_key=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[str] = mapped_column(String(100), default='')


class WalletFunding(Base):
    __tablename__ = 'customer_wallet_funding'
    __table_args__ = (Index('ix_wallet_funding_owner', 'customer_id', 'created_at'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'))
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_reference: Mapped[str | None] = mapped_column(String(120), unique=True)
    provider_settings_id: Mapped[int | None]
    environment: Mapped[str] = mapped_column(String(12), default='sandbox')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(15), default='pending')
    checkout_url: Mapped[str] = mapped_column(String(2000), default='')
    created_at: Mapped[datetime] = mapped_column(default=now)
    completed_at: Mapped[datetime | None]


class WalletCheckout(Base):
    __tablename__ = 'customer_wallet_checkout'
    funding_id: Mapped[str] = mapped_column(ForeignKey('customer_wallet_funding.id', ondelete='CASCADE'), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, default='{}')
    payment_reference: Mapped[str | None] = mapped_column(String(120))


class WalletRefund(Base):
    __tablename__ = 'customer_wallet_refunds'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(String(500))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(default=now)


class AdminPermission(Base):
    __tablename__ = 'account_admin_permissions'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    support_edit: Mapped[bool] = mapped_column(default=True)
    gateway_edit: Mapped[bool] = mapped_column(default=True)
    review_moderate: Mapped[bool] = mapped_column(default=True)
    audit_rollback: Mapped[bool] = mapped_column(default=False)


class EnterpriseAudit(Identity, Base):
    __tablename__ = 'enterprise_admin_audit'
    __table_args__ = (Index('ix_enterprise_audit_filter', 'created_at', 'module', 'actor_id'),)
    actor_id: Mapped[int | None] = mapped_column(index=True)
    actor_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(80))
    module: Mapped[str] = mapped_column(String(80))
    entity_key: Mapped[str] = mapped_column(Text, default='{}')
    old_value: Mapped[str] = mapped_column(Text, default='{}')
    new_value: Mapped[str] = mapped_column(Text, default='{}')
    reason: Mapped[str] = mapped_column(String(500), default='')
    ip_address: Mapped[str] = mapped_column(String(80), default='')
    device: Mapped[str] = mapped_column(String(500), default='')
    status: Mapped[str] = mapped_column(String(20), default='success')
    rollback_of_id: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=now)
