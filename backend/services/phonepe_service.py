import base64
import hashlib
import json
import os
import time
import uuid
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.db import Session
from backend.models import Order, DeliveryStatus, now
from backend.payment_models import Payment, PaymentOrder, PaymentEvent, Refund, AdminSettings, PaymentMethod
from backend.services import admin_payment_service as admin, order_service
from backend.services.geo_service import detect_country
from backend.utils.signature import encode_payload, x_verify, verify_sha_webhook, verify_legacy_callback

SANDBOX = 'https://api-preprod.phonepe.com/apis/pg-sandbox'
PRODUCTION = 'https://api.phonepe.com/apis/pg'
TOKEN_CACHE = {}


class Gateway:
    def __init__(self, row):
        self.row = row
        self.cfg = admin.credentials(row)
        self.base = SANDBOX if row.environment == 'sandbox' else PRODUCTION
        if row.api_version == 'v1' and row.environment == 'production':
            self.base = 'https://api.phonepe.com/apis/hermes'

    def request(self, method, path, payload=None):
        headers = {'Content-Type': 'application/json'}
        body = payload
        if self.row.api_version == 'v1':
            encoded = encode_payload(payload) if payload is not None else ''
            headers.update({'X-VERIFY': x_verify(encoded, path, self.cfg['salt_key'], self.cfg.get('salt_index', 1)), 'X-MERCHANT-ID': self.cfg['merchant_id']})
            body = {'request': encoded} if payload is not None else None
        else:
            headers['Authorization'] = 'O-Bearer ' + self.token()
        try:
            with httpx.Client(timeout=20, trust_env=False) as client:
                response = client.request(method, self.base + path, headers=headers, json=body)
            if response.status_code == 401 and self.row.api_version == 'v2':
                TOKEN_CACHE.pop(self.row.id, None)
                raise HTTPException(502, 'PhonePe credentials expired or were rejected. Re-check status before retrying.')
            if response.is_error:
                raise HTTPException(502, 'PhonePe could not process this request. Re-check its status before retrying.')
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            if self.row.api_version == 'v1':
                if not data.get('success') and data.get('code') not in {'PAYMENT_PENDING', 'PAYMENT_ERROR', 'PAYMENT_DECLINED'}:
                    raise HTTPException(502, 'PhonePe rejected the request')
                data = {**data.get('data', {}), 'code': data.get('code')}
            return data
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(502, 'PhonePe is temporarily unavailable. The transaction status will be reconciled.')

    def token(self):
        cached = TOKEN_CACHE.get(self.row.id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        url = SANDBOX + '/v1/oauth/token' if self.row.environment == 'sandbox' else 'https://api.phonepe.com/apis/identity-manager/v1/oauth/token'
        try:
            with httpx.Client(timeout=20, trust_env=False) as client:
                response = client.post(url, data={'client_id': self.cfg['client_id'], 'client_secret': self.cfg['client_secret'],
                    'client_version': self.cfg.get('client_version', 1), 'grant_type': 'client_credentials'})
            if response.is_error:
                raise HTTPException(502, 'PhonePe authorization failed. Check the selected environment and credentials.')
            data = response.json()
            TOKEN_CACHE[self.row.id] = (data['access_token'], int(data['expires_at']))
            return data['access_token']
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(502, 'PhonePe authorization is unavailable')

    def pay(self, payment, instrument):
        origin = os.environ.get('PHONEPE_CUSTOMER_ORIGIN', 'https://customer.dashvanti.com').rstrip('/')
        redirect = origin + f'/customer/payment/{payment.id}'
        if not origin.startswith('https://'):
            raise HTTPException(503, 'PhonePe redirect must use HTTPS')
        if self.row.api_version == 'v1':
            return self.request('POST', '/pg/v1/pay', {'merchantId': self.cfg['merchant_id'],
                'merchantTransactionId': payment.merchant_order_id, 'merchantUserId': str(payment.user_id),
                'amount': payment.amount, 'redirectUrl': redirect, 'redirectMode': 'REDIRECT',
                'callbackUrl': origin + '/api/phonepe/callback', 'paymentInstrument': {'type': 'PAY_PAGE'}})
        flow = {'type': 'PG_CHECKOUT', 'merchantUrls': {'redirectUrl': redirect}}
        if instrument != 'REDIRECT':
            modes = ['UPI_INTENT'] if instrument == 'UPI_INTENT' else ['UPI_INTENT', 'UPI_QR']
            flow['paymentModeConfig'] = {'enabledPaymentModes': [{'type': item} for item in modes]}
        return self.request('POST', '/checkout/v2/pay', {'merchantOrderId': payment.merchant_order_id,
            'amount': payment.amount, 'expireAfter': 1200, 'paymentFlow': flow})

    def status(self, payment):
        path = f'/checkout/v2/order/{payment.merchant_order_id}/status?details=true'
        if self.row.api_version == 'v1':
            path = f"/pg/v1/status/{self.cfg['merchant_id']}/{payment.merchant_order_id}"
        return self.request('GET', path)

    def refund(self, payment, refund):
        if self.row.api_version == 'v1':
            return self.request('POST', '/pg/v1/refund', {'merchantId': self.cfg['merchant_id'],
                'merchantTransactionId': refund.merchant_refund_id, 'originalTransactionId': payment.merchant_order_id,
                'amount': refund.amount, 'callbackUrl': os.environ.get('PHONEPE_CUSTOMER_ORIGIN', 'https://customer.dashvanti.com').rstrip('/') + '/api/phonepe/callback'})
        return self.request('POST', '/payments/v2/refund', {'merchantRefundId': refund.merchant_refund_id,
            'originalMerchantOrderId': payment.merchant_order_id, 'amount': refund.amount})

    def refund_status(self, refund):
        path = f'/payments/v2/refund/{refund.merchant_refund_id}/status'
        if self.row.api_version == 'v1':
            path = f"/pg/v1/status/{self.cfg['merchant_id']}/{refund.merchant_refund_id}"
        return self.request('GET', path)


def methods(db, request, user):
    country = detect_country(request, user)
    allowed = [{'id': 'cash', 'name': 'Cash on delivery / pickup'}]
    method = db.get(PaymentMethod, 'phonepe')
    if country == 'IN' and method and method.enabled and admin.configured(admin.active_settings(db)):
        allowed.append({'id': 'phonepe', 'name': 'PhonePe / UPI', 'currency': 'INR', 'environment': admin.active_settings(db).environment})
    return {'country': country, 'methods': allowed}


def payment_result(db, payment):
    return {**admin.public_payment(db, payment), 'redirect_url': payment.redirect_url}


def pay(db, request, user, data):
    if detect_country(request, user) != 'IN':
        raise HTTPException(403, 'PhonePe is available only in India')
    method = db.scalar(select(PaymentMethod).where(PaymentMethod.name == 'phonepe').with_for_update())
    settings = admin.active_settings(db)
    if not method or not method.enabled or not admin.configured(settings):
        raise HTTPException(503, 'PhonePe is not enabled or its credentials are incomplete')
    request_key = f'{user.id}:{data.checkout.request_key[:48]}'
    existing = db.scalar(select(Payment).where(Payment.request_key == request_key))
    if existing:
        return payment_result(db, existing)
    cfg = Gateway(settings)
    result = order_service.checkout(db, user, data.checkout.model_copy(update={'payment_mode': 'PhonePe'}))
    orders = list(db.scalars(select(Order).where(Order.id.in_(result['order_ids']))))
    if not orders or any(order.currency != 'INR' or order.status != 'PAYMENT_PENDING' for order in orders):
        raise HTTPException(409, 'PhonePe requires unpaid INR orders. Dollar prices are never converted automatically.')
    amount = int(sum(order.total for order in orders) * 100)
    if amount < 100:
        raise HTTPException(400, 'PhonePe minimum payment is INR 1')
    payment = Payment(merchant_order_id='DV_' + uuid.uuid4().hex, user_id=user.id, settings_id=settings.id,
        request_key=request_key, amount=amount, country='IN', currency='INR', environment=settings.environment, api_version=settings.api_version)
    db.add(payment)
    db.flush()
    for order in orders:
        db.add(PaymentOrder(payment_id=payment.id, order_id=order.id, original_order_id=order.id))
    admin.audit(db, 'payment_requested', payment.id, amount=amount, currency='INR', environment=settings.environment)
    db.commit()
    try:
        response = cfg.pay(payment, data.instrument)
        redirect = response.get('redirectUrl') or response.get('instrumentResponse', {}).get('redirectInfo', {}).get('url')
        parsed = urlparse(redirect or '')
        if parsed.scheme != 'https' or not parsed.hostname or not (parsed.hostname == 'phonepe.com' or parsed.hostname.endswith('.phonepe.com')):
            raise HTTPException(502, 'PhonePe did not return a valid checkout URL')
        payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
        payment.redirect_url = redirect
        payment.provider_order_id = response.get('orderId')
        payment.expires_at = response.get('expireAt') or int((time.time() + 1200) * 1000)
        if payment.status in {'INITIATING', 'UNKNOWN'}:
            payment.status = 'PENDING'
        admin.audit(db, 'checkout_created', payment.id)
        db.commit()
        return payment_result(db, payment)
    except HTTPException:
        db.refresh(payment)
        if payment.status == 'INITIATING':
            payment.status = 'UNKNOWN'
        admin.audit(db, 'payment_request_uncertain', payment.id)
        db.commit()
        raise


def payment_owned(db, transaction_id, user):
    payment = admin.transaction(db, transaction_id)
    if payment.user_id != user.id:
        raise HTTPException(404, 'Payment not found')
    return payment


def normalized_state(response, version):
    if version == 'v1':
        return {'PAYMENT_SUCCESS': 'COMPLETED', 'PAYMENT_ERROR': 'FAILED', 'PAYMENT_DECLINED': 'FAILED', 'PAYMENT_PENDING': 'PENDING'}.get(response.get('code'), response.get('state', 'PENDING'))
    return response.get('state', 'PENDING')


def apply_status(db, transaction_id, response):
    payment = db.scalar(select(Payment).where(Payment.id == transaction_id).with_for_update())
    state = normalized_state(response, payment.api_version)
    if state not in {'COMPLETED', 'FAILED', 'PENDING'}:
        raise HTTPException(502, 'Unrecognized PhonePe status')
    if state == 'COMPLETED' and payment.api_version == 'v2' and not response.get('orderId'):
        raise HTTPException(502, 'PhonePe order reference is missing')
    if payment.provider_order_id and response.get('orderId') and response['orderId'] != payment.provider_order_id:
        raise HTTPException(502, 'PhonePe order reference mismatch')
    if payment.api_version == 'v1' and (response.get('merchantId') != Gateway(db.get(AdminSettings, payment.settings_id)).cfg['merchant_id'] or response.get('merchantTransactionId') != payment.merchant_order_id):
        raise HTTPException(502, 'PhonePe merchant reference mismatch')
    if state == 'COMPLETED' and (type(response.get('amount')) is not int or response['amount'] != payment.amount):
        raise HTTPException(502, 'PhonePe payment amount mismatch')
    if payment.status == 'COMPLETED':
        from backend.services.driver_deposit_service import sync
        sync(db, payment)
        payment.checked_at = now()
        return payment
    previous = payment.status
    payment.status = state
    payment.checked_at = now()
    orders = db.scalars(select(Order).join(PaymentOrder, PaymentOrder.order_id == Order.id).where(PaymentOrder.payment_id == payment.id).with_for_update(of=Order))
    for order in orders:
        if state == 'COMPLETED' and order.status in {'PAYMENT_PENDING', 'PAYMENT_FAILED'}:
            order.status = 'SANDBOX_PAID' if payment.environment == 'sandbox' else 'PLACED'
            db.add(DeliveryStatus(order_id=order.id, status=order.status))
            if payment.environment == 'production':
                from backend.services.kafka_event_service import emit
                emit(db, 'ORDER_CREATED', {'order_id': order.id, 'restaurant_id': order.restaurant_id})
                from backend.services.restaurant_auto_accept_service import accept_order
                accept_order(db, order)
        elif state == 'FAILED' and order.status == 'PAYMENT_PENDING':
            order.status = 'PAYMENT_FAILED'
    from backend.services.driver_deposit_service import sync
    sync(db, payment)
    if previous != state:
        admin.audit(db, 'payment_status_verified', payment.id, previous=previous, status=state, amount=payment.amount)
    return payment


def recheck(db, payment):
    response = Gateway(db.get(AdminSettings, payment.settings_id)).status(payment)
    return apply_status(db, payment.id, response)


def refund(db, payment, data):
    payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
    existing = db.scalar(select(Refund).where(Refund.payment_id == payment.id, Refund.request_key == data.request_key))
    if existing:
        if existing.amount != data.amount:
            raise HTTPException(409, 'This refund request key already uses a different amount')
        return admin.refund_view(existing)
    if payment.status != 'COMPLETED':
        raise HTTPException(409, 'Only verified completed payments can be refunded')
    reserved = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.payment_id == payment.id, Refund.status != 'FAILED'))
    if reserved + data.amount > payment.amount:
        raise HTTPException(409, 'Refund exceeds the unreserved payment amount')
    row = Refund(payment_id=payment.id, merchant_refund_id='DVR_' + uuid.uuid4().hex,
        request_key=data.request_key, amount=data.amount, reason=data.reason)
    db.add(row)
    db.flush()
    admin.audit(db, 'refund_requested', payment.id, refund_id=row.id, amount=row.amount, reason=row.reason)
    db.commit()
    try:
        response = Gateway(db.get(AdminSettings, payment.settings_id)).refund(payment, row)
        row = db.scalar(select(Refund).where(Refund.id == row.id).with_for_update())
        row.provider_refund_id = response.get('refundId')
        if row.status in {'REQUESTED', 'UNKNOWN'}:
            row.status = 'PENDING'
        db.commit()
        return admin.refund_view(row)
    except HTTPException:
        db.refresh(row)
        if row.status == 'REQUESTED':
            row.status = 'UNKNOWN'
        admin.audit(db, 'refund_request_uncertain', payment.id, refund_id=row.id)
        db.commit()
        raise


def recheck_refund(db, refund_id):
    row = db.get(Refund, refund_id)
    if not row:
        raise HTTPException(404, 'Refund not found')
    payment = db.get(Payment, row.payment_id)
    response = Gateway(db.get(AdminSettings, payment.settings_id)).refund_status(row)
    state = normalized_state(response, payment.api_version)
    if state not in {'COMPLETED', 'FAILED', 'PENDING'}:
        raise HTTPException(502, 'Unrecognized refund status')
    if state == 'COMPLETED' and (response.get('amount') != row.amount or (payment.api_version == 'v2' and response.get('originalMerchantOrderId') != payment.merchant_order_id)):
        raise HTTPException(502, 'PhonePe refund amount or reference mismatch')
    if state == 'COMPLETED' and row.provider_refund_id and response.get('refundId') != row.provider_refund_id:
        raise HTTPException(502, 'PhonePe refund reference mismatch')
    if payment.api_version == 'v1' and response.get('merchantTransactionId') != row.merchant_refund_id:
        raise HTTPException(502, 'PhonePe refund transaction mismatch')
    row = db.scalar(select(Refund).where(Refund.id == row.id).with_for_update())
    if row.status != 'COMPLETED':
        if row.status != state:
            admin.audit(db, 'refund_status_verified', row.payment_id, refund_id=row.id, status=state, amount=row.amount)
        row.status = state
    row.checked_at = now()
    return admin.refund_view(row)


def receive_callback(db, raw, headers):
    if len(raw) > 65536:
        raise HTTPException(413, 'Callback is too large')
    try:
        envelope = json.loads(raw)
        legacy = envelope.get('response')
        decoded = json.loads(base64.b64decode(legacy, validate=True)) if legacy else envelope
        payload = decoded.get('data', {}) if legacy else envelope.get('payload', {})
        merchant_ref = payload.get('merchantOrderId') or payload.get('merchantTransactionId')
        refund_ref = payload.get('merchantRefundId')
        refund_row = db.scalar(select(Refund).where(Refund.merchant_refund_id == (refund_ref or merchant_ref)))
        payment = db.get(Payment, refund_row.payment_id) if refund_row else db.scalar(select(Payment).where(Payment.merchant_order_id == merchant_ref))
        if not payment:
            raise HTTPException(404, 'Unknown payment callback')
        cfg = admin.credentials(db.get(AdminSettings, payment.settings_id))
        valid = verify_legacy_callback(legacy, headers.get('x-verify', ''), cfg.get('salt_key', ''), cfg.get('salt_index', 1)) if legacy and payment.api_version == 'v1' else verify_sha_webhook(headers.get('authorization', ''), cfg.get('webhook_username'), cfg.get('webhook_password')) if not legacy and payment.api_version == 'v2' else False
        if not valid:
            raise HTTPException(401, 'Invalid PhonePe callback authentication')
    except (ValueError, TypeError, AttributeError, KeyError):
        raise HTTPException(400, 'Malformed PhonePe callback')
    dedup = hashlib.sha256(raw).hexdigest()
    if not db.scalar(select(PaymentEvent.id).where(PaymentEvent.dedup_key == dedup)):
        from sqlalchemy.dialects.postgresql import insert
        values = dict(payment_id=payment.id, event='callback_received', dedup_key=dedup,
            details=json.dumps({'refund_id': refund_row.id if refund_row else None, 'provider_event': str(envelope.get('event', 'legacy'))[:80]}))
        if db.bind.dialect.name == 'postgresql':
            db.execute(insert(PaymentEvent).values(**values).on_conflict_do_nothing(index_elements=['dedup_key']))
        else:
            db.add(PaymentEvent(**values))
    db.commit()
    return payment.id, refund_row.id if refund_row else None


def reconcile(transaction_id, refund_id=None):
    with Session() as db:
        try:
            payment = db.get(Payment, transaction_id)
            if not payment:
                return
            recheck_refund(db, refund_id) if refund_id else recheck(db, payment)
            db.commit()
        except HTTPException:
            db.rollback()
            if refund_id:
                row = db.get(Refund, refund_id)
            else:
                row = db.get(Payment, transaction_id)
            if row:
                row.checked_at = now()
                db.commit()
