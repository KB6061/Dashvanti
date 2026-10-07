import hashlib
import secrets
import re
from datetime import timedelta
import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import select, func
from backend.config import settings
from backend.models import User, Customer, Restaurant, Driver, PasswordReset, now
from backend.services.kafka_event_service import emit

passwords = PasswordHash.recommended()
DUMMY = passwords.hash('dummy-password-for-timing-only')

def register(db, data):
    consent = None
    if data.role == 'driver':
        from backend.services.driver_agreement_service import registration_consent
        consent = registration_consent(db, data)
    if (data.latitude is None)!=(data.longitude is None):
        raise HTTPException(422,'Provide both location coordinates')
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    user = User(email=email, password=passwords.hash(data.password), role=data.role, name=data.name, phone=data.phone)
    db.add(user)
    db.flush()
    profile = {'customer': Customer, 'restaurant': Restaurant, 'driver': Driver}[data.role]
    db.add(profile(id=user.id, **({'name': data.name} if data.role == 'restaurant' else {})))
    if data.role=='customer' and data.latitude is not None:
        from backend.schemas import CustomerLocationInput
        from backend.services.user_service import save_current_location
        db.flush()
        save_current_location(db,user,CustomerLocationInput(latitude=data.latitude,longitude=data.longitude))
    if data.role == 'driver':
        db.flush()
        from backend.services.driver_partner_service import partner
        partner(db, user.id)
        consent.driver_id = user.id
        consent.registered_at = now()
    emit(db, 'USER_REGISTERED', {'user_id': user.id, 'role': user.role})
    return {'id': user.id}

def login(db, data):
    identifier = str(data.email).strip().lower()
    user = db.scalar(select(User).where(User.email == identifier))
    if not user and '@' not in identifier:
        digits = re.sub(r'[^0-9]', '', identifier)
        if 7 <= len(digits) <= 15:
            matches = list(db.scalars(select(User).where(User.role == data.role,
                func.regexp_replace(User.phone, '[^0-9]', '', 'g') == digits).limit(2)))
            user = matches[0] if len(matches) == 1 else None
    valid = passwords.verify(data.password, user.password if user else DUMMY)
    if not valid or not user or user.role != data.role:
        raise HTTPException(401, 'Invalid credentials')
    from backend.services.session_service import issue_tokens
    emit(db, 'USER_LOGGED_IN', {'user_id': user.id})
    return issue_tokens(user)

def forgot(db, data):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user:
        token = secrets.token_urlsafe(40)
        db.add(PasswordReset(user_id=user.id, digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=now()+timedelta(minutes=30)))
        # A dedicated mail outbox is consumed without publishing its secret to Kafka.
        emit(db, 'MAIL_PASSWORD_RESET', {'email': user.email, 'url': f'{settings.public_url}/{user.role}/reset?token={token}'})
        emit(db, 'PASSWORD_RESET_REQUESTED', {'user_id': user.id})
    return {'message': 'If the account exists, a reset link will be emailed.'}

def reset(db, data):
    row = db.scalar(select(PasswordReset).where(PasswordReset.digest == hashlib.sha256(data.token.encode()).hexdigest()).with_for_update())
    if not row or row.used or row.expires_at < now():
        raise HTTPException(400, 'Invalid or expired reset token')
    user = db.get(User, row.user_id)
    user.password = passwords.hash(data.password)
    user.token_version += 1
    row.used = True
    return {'message': 'Password updated'}
