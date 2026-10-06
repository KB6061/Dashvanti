import hashlib
import secrets
from datetime import timedelta
import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import select
from backend.config import settings
from backend.models import User, Customer, Restaurant, Driver, PasswordReset, now
from backend.services.kafka_event_service import emit

passwords = PasswordHash.recommended()
DUMMY = passwords.hash('dummy-password-for-timing-only')

def register(db, data):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    user = User(email=email, password=passwords.hash(data.password), role=data.role, name=data.name, phone=data.phone)
    db.add(user)
    db.flush()
    profile = {'customer': Customer, 'restaurant': Restaurant, 'driver': Driver}[data.role]
    db.add(profile(id=user.id, **({'name': data.name} if data.role == 'restaurant' else {})))
    emit(db, 'USER_REGISTERED', {'user_id': user.id, 'role': user.role})
    return {'id': user.id}

def login(db, data):
    identifier = str(data.email).strip().lower()
    user = db.scalar(select(User).where(User.email == identifier))
    if not user:
        user = db.scalar(select(User).where(User.phone == identifier))
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
