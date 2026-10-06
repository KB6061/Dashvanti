from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base
from backend.models import Identity, now


class SocialIdentity(Identity, Base):
    __tablename__ = 'social_identities'
    __table_args__ = (UniqueConstraint('provider', 'provider_user_id'),)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    profile_picture: Mapped[str | None] = mapped_column(String(2048))
    last_login_at: Mapped[datetime] = mapped_column(default=now)


class SocialChallenge(Base):
    __tablename__ = 'social_challenges'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
