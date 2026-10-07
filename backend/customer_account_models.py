from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now

class CustomerProfile(Base):
    __tablename__ = 'customer_profiles'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80), default='')
    last_name: Mapped[str] = mapped_column(String(80), default='')
    date_of_birth: Mapped[date | None]
    gender: Mapped[str] = mapped_column(String(30), default='prefer_not_to_say')
    language: Mapped[str] = mapped_column(String(20), default='en')
    state: Mapped[str] = mapped_column(String(100), default='')
    city: Mapped[str] = mapped_column(String(100), default='')
    timezone: Mapped[str] = mapped_column(String(80), default='America/Chicago')
    timezone_detected: Mapped[bool] = mapped_column(default=False)
    theme: Mapped[str] = mapped_column(String(10), default='system')
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime | None]

class CustomerAddressDetails(Base):
    __tablename__ = 'customer_address_details'
    address_id: Mapped[int] = mapped_column(ForeignKey('addresses.id', ondelete='CASCADE'), primary_key=True)
    address_type: Mapped[str] = mapped_column(String(10), default='Home')
    apartment: Mapped[str] = mapped_column(String(100), default='')
    landmark: Mapped[str] = mapped_column(String(150), default='')
    zip_code: Mapped[str] = mapped_column(String(20), default='')
    instructions: Mapped[str] = mapped_column(String(500), default='')

class CustomerFavorite(Base):
    __tablename__ = 'customer_favorites'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurants.id', ondelete='CASCADE'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerWallet(Base):
    __tablename__ = 'customer_wallets'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12,2), default=0)

class CustomerWalletTransaction(Identity, Base):
    __tablename__ = 'customer_wallet_transactions'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    kind: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(String(300), default='')
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerPaymentMethod(Identity, Base):
    __tablename__ = 'customer_payment_methods'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_customer_id: Mapped[str] = mapped_column(String(120))
    provider_token: Mapped[str] = mapped_column(String(120), unique=True)
    brand: Mapped[str] = mapped_column(String(30))
    last4: Mapped[str] = mapped_column(String(4))
    exp_month: Mapped[int]
    exp_year: Mapped[int]
    is_default: Mapped[bool] = mapped_column(default=False)

class CustomerReward(Identity, Base):
    __tablename__ = 'customer_rewards'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    points: Mapped[int]
    description: Mapped[str] = mapped_column(String(300))
    reference: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerCoupon(Base):
    __tablename__ = 'customer_coupons'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey('promotions.id', ondelete='CASCADE'), primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(default=now)

class CustomerReferral(Base):
    __tablename__ = 'customer_referrals'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey('customers.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerNotificationSettings(Base):
    __tablename__ = 'customer_notification_settings'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    order_updates: Mapped[bool] = mapped_column(default=True)
    delivery_alerts: Mapped[bool] = mapped_column(default=True)
    sms: Mapped[bool] = mapped_column(default=True)
    email: Mapped[bool] = mapped_column(default=True)
    push: Mapped[bool] = mapped_column(default=True)
    promotions: Mapped[bool] = mapped_column(default=False)
    referral_rewards: Mapped[bool] = mapped_column(default=True)
    system_alerts: Mapped[bool] = mapped_column(default=True)

class CustomerSupportReply(Identity, Base):
    __tablename__ = 'customer_support_replies'
    ticket_id: Mapped[int] = mapped_column(ForeignKey('support_tickets.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerLoginHistory(Identity, Base):
    __tablename__ = 'customer_login_history'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    ip_address: Mapped[str] = mapped_column(String(80), default='')
    user_agent: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(default=now)

class CustomerDevice(Identity, Base):
    __tablename__ = 'customer_devices'
    __table_args__ = (UniqueConstraint('customer_id','fingerprint'),)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    information: Mapped[str] = mapped_column(String(500))
    last_seen: Mapped[datetime] = mapped_column(default=now)

class CustomerSecurity(Base):
    __tablename__ = 'customer_security'
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    totp_secret: Mapped[str | None] = mapped_column(String(500))
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    last_totp_step: Mapped[int] = mapped_column(default=-1)
    deletion_requested_at: Mapped[datetime | None]
