import json
import os
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.models import Restaurant
from backend.payment_models import Payment, Refund, AdminSettings, PaymentMethod, PaymentEvent, PaymentOrder, Settlement

SECRET_FIELDS = {'salt_key', 'api_key', 'client_secret', 'webhook_password'}
CREDENTIAL_FIELDS = {'merchant_id', 'salt_key', 'salt_index', 'api_key', 'client_id', 'client_secret', 'client_version', 'webhook_username', 'webhook_password'}


def cipher():
    key = os.environ.get('PAYMENT_ENCRYPTION_KEY', '')
    if not key:
        raise HTTPException(503, 'Payment credential encryption is not configured')
    return Fernet(key.encode())


def credentials(row):
    return json.loads(cipher().decrypt(row.encrypted_credentials.encode()))


def audit(db, event, payment_id=None, **details):
    db.add(PaymentEvent(payment_id=payment_id, event=event, details=json.dumps(details)))


def active_settings(db):
    method = db.get(PaymentMethod, 'phonepe')
    return db.get(AdminSettings, method.settings_id) if method and method.settings_id else None


def configured(row):
    if not row:
        return False
    cfg = credentials(row)
    names = ('client_id', 'client_secret', 'webhook_username', 'webhook_password') if row.api_version == 'v2' else ('merchant_id', 'salt_key')
    return all(cfg.get(name) for name in names)


def settings_view(db):
    row = active_settings(db)
    cfg = credentials(row) if row else {}
    return {'environment': row.environment if row else 'sandbox', 'api_version': row.api_version if row else 'v2',
        'credentials': {key: bool(value) if key in SECRET_FIELDS else value for key, value in cfg.items()},
        'configured': configured(row), 'methods': [{'method': item.name, 'enabled': item.enabled,
            'configured': configured(row) if item.name == 'phonepe' else False} for item in db.scalars(select(PaymentMethod).order_by(PaymentMethod.name))]}


def update_settings(db, data):
    if data.environment == 'production' and not data.confirm_production:
        raise HTTPException(400, 'Confirm production mode explicitly')
    previous = active_settings(db)
    cfg = credentials(previous) if previous and previous.environment == data.environment and previous.api_version == data.api_version else {}
    for name, value in data.model_dump().items():
        if name in CREDENTIAL_FIELDS and value is not None and value != '':
            cfg[name] = value.strip() if isinstance(value, str) else value
    row = AdminSettings(environment=data.environment, api_version=data.api_version,
        encrypted_credentials=cipher().encrypt(json.dumps(cfg).encode()).decode())
    db.add(row)
    db.flush()
    method = db.get(PaymentMethod, 'phonepe')
    method.settings_id = row.id
    audit(db, 'settings_updated', environment=row.environment, api_version=row.api_version, settings_id=row.id)
    return {'saved': True, 'configured': configured(row)}


def toggle(db, data):
    method = db.get(PaymentMethod, data.method)
    method.enabled = data.enabled
    if data.method=='phonepe':
        from backend.account_enhancement_models import GatewayControl
        control=db.get(GatewayControl,'phonepe')
        if not control:control=GatewayControl(name='phonepe',countries='IN');db.add(control)
        control.enabled=data.enabled
    audit(db, 'method_toggled', method=data.method, enabled=data.enabled)
    return {'method': method.name, 'enabled': method.enabled, 'configured': configured(active_settings(db)) if method.name == 'phonepe' else False}


def public_payment(db, row):
    orders = list(db.scalars(select(PaymentOrder.original_order_id).where(PaymentOrder.payment_id == row.id)))
    refunded = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == row.id, Refund.status == 'COMPLETED'))
    reserved = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == row.id, Refund.status != 'FAILED'))
    from decimal import Decimal
    return {'id': row.id, 'merchant_order_id': row.merchant_order_id, 'provider': row.provider,
        'user_id': row.user_id, 'amount': row.amount, 'amount_major': str(Decimal(row.amount) / 100), 'currency': row.currency, 'country': row.country,
        'environment': row.environment, 'status': row.status, 'order_ids': orders, 'refunded_amount': refunded,
        'refundable_amount': max(0, row.amount - reserved), 'checked_at': row.checked_at, 'created_at': row.created_at}


def refund_view(row):
    return {'id': row.id, 'payment_id': row.payment_id, 'merchant_refund_id': row.merchant_refund_id,
        'provider_refund_id': row.provider_refund_id, 'amount': row.amount, 'status': row.status,
        'reason': row.reason, 'created_at': row.created_at, 'checked_at': row.checked_at}


def transaction(db, transaction_id):
    row = db.get(Payment, transaction_id)
    if not row:
        raise HTTPException(404, 'Payment not found')
    return row


def detail(db, transaction_id):
    row = transaction(db, transaction_id)
    return {**public_payment(db, row), 'refunds': [refund_view(r) for r in db.scalars(select(Refund).where(Refund.payment_id == row.id).order_by(Refund.id.desc()))],
        'events': [{'event': e.event, 'details': json.loads(e.details), 'created_at': e.created_at} for e in db.scalars(select(PaymentEvent).where(PaymentEvent.payment_id == row.id).order_by(PaymentEvent.id.desc()).limit(100))]}


def transactions(db, offset=0, limit=50, status=None):
    query = select(Payment)
    if status:
        query = query.where(Payment.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Payment.id.desc()).offset(offset).limit(limit))
    return {'total': total, 'offset': offset, 'limit': limit, 'transactions': [public_payment(db, row) for row in rows]}


def set_restaurant_currency(db, data):
    if not data.confirm_prices:
        raise HTTPException(400, 'Confirm menu prices and fees are already expressed in the selected currency; no conversion is performed')
    row = db.get(Restaurant, data.restaurant_id)
    if not row:
        raise HTTPException(404, 'Restaurant not found')
    row.currency = data.currency
    audit(db, 'restaurant_currency_updated', restaurant_id=row.id, currency=row.currency)
    return {'restaurant_id': row.id, 'currency': row.currency}


def settlements(db, offset=0, limit=50):
    rows = list(db.scalars(select(Settlement).order_by(Settlement.id.desc()).offset(offset).limit(limit)))
    return {'source': 'merchant_report', 'note': 'Settlement reports are imported from the merchant dashboard. Sandbox does not settle real funds.',
        'total': db.scalar(select(func.count()).select_from(Settlement)), 'items': [
            {key: getattr(row, key) for key in ('id', 'reference', 'provider', 'environment', 'amount', 'currency', 'status', 'settled_at', 'source')} for row in rows]}


def import_settlement(db, data):
    row = db.scalar(select(Settlement).where(Settlement.reference == data.reference))
    if not row:
        row = Settlement(**data.model_dump())
        db.add(row)
    else:
        for key, value in data.model_dump().items():
            setattr(row, key, value)
    audit(db, 'settlement_imported', reference=data.reference, environment=data.environment)
    return {'saved': True, 'reference': data.reference}
