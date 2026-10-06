import uuid
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select
from backend.payment_models import Payment, Refund, AdminSettings, PaymentMethod
from backend.models_driver_partner import DriverDeposit
from backend.models import Order
from backend.services import admin_payment_service as admin, phonepe_service as phonepe
from backend.services.driver_partner_service import partner, unseal, notice


def pay(db, user):
    application = partner(db, user.id, True)
    if application.status != 'APPROVED' or application.account_status != 'ACTIVE': raise HTTPException(409, 'Admin approval is required before paying the deposit')
    current = db.scalar(select(DriverDeposit).where(DriverDeposit.driver_id == user.id, DriverDeposit.status.in_(['PAID', 'PENDING', 'UNKNOWN'])).order_by(DriverDeposit.id.desc()))
    if current:
        payment = db.get(Payment, current.payment_id)
        return {'deposit_id': current.id, 'payment_id': payment.id, 'status': current.status, 'redirect_url': payment.redirect_url}
    cfg = admin.active_settings(db)
    method = db.get(PaymentMethod, 'phonepe')
    if not cfg or not method.enabled or not admin.configured(cfg): raise HTTPException(503, 'Configure and enable PhonePe credentials in Admin Payments first')
    amount = Decimal(3000 if unseal(application.profile).get('vehicle_type') == 'Car' else 1000)
    payment = Payment(merchant_order_id='DVD_'+uuid.uuid4().hex, user_id=user.id, settings_id=cfg.id, request_key='deposit:'+uuid.uuid4().hex, amount=int(amount*100), country='IN', currency='INR', environment=cfg.environment, api_version=cfg.api_version)
    db.add(payment); db.flush()
    deposit = DriverDeposit(driver_id=user.id, payment_id=payment.id, amount=amount)
    db.add(deposit); db.flush(); db.commit()
    gateway = phonepe.Gateway(cfg)
    redirect = f'https://driver.dashvanti.com/driver/partner?payment_id={payment.id}'
    try:
        if cfg.api_version == 'v2':
            result = gateway.request('POST', '/checkout/v2/pay', {'merchantOrderId': payment.merchant_order_id, 'amount': payment.amount, 'expireAfter': 1200, 'paymentFlow': {'type': 'PG_CHECKOUT', 'merchantUrls': {'redirectUrl': redirect}}})
        else:
            result = gateway.request('POST', '/pg/v1/pay', {'merchantId': gateway.cfg['merchant_id'], 'merchantTransactionId': payment.merchant_order_id, 'merchantUserId': str(user.id), 'amount': payment.amount, 'redirectUrl': redirect, 'redirectMode': 'REDIRECT', 'callbackUrl': 'https://driver.dashvanti.com/api/phonepe/callback', 'paymentInstrument': {'type': 'PAY_PAGE'}})
        url = result.get('redirectUrl') or result.get('instrumentResponse', {}).get('redirectInfo', {}).get('url')
        parsed = urlparse(url or '')
        if parsed.scheme != 'https' or not parsed.hostname or not (parsed.hostname == 'phonepe.com' or parsed.hostname.endswith('.phonepe.com')): raise HTTPException(502, 'Invalid PhonePe redirect')
        payment.redirect_url = url; payment.provider_order_id = result.get('orderId'); payment.status = 'PENDING'
        db.commit()
    except HTTPException:
        payment.status = 'UNKNOWN'; deposit.status = 'UNKNOWN'; db.commit(); raise
    return {'deposit_id': deposit.id, 'payment_id': payment.id, 'status': deposit.status, 'redirect_url': payment.redirect_url}


def sync(db, payment):
    deposit = db.scalar(select(DriverDeposit).where(DriverDeposit.payment_id == payment.id).with_for_update())
    if not deposit or deposit.status in {'REFUNDED', 'REFUND_PENDING'}: return
    previous = deposit.status
    deposit.status = ('PAID' if payment.environment == 'production' else 'SANDBOX_PAID') if payment.status == 'COMPLETED' else payment.status
    if previous != deposit.status and deposit.status == 'PAID': notice(db, deposit.driver_id, 'DEPOSIT_PAID', 'Your refundable driver security deposit has been confirmed.')


def recheck(db, driver_id, deposit_id):
    deposit = db.get(DriverDeposit, deposit_id)
    if not deposit or deposit.driver_id != driver_id: raise HTTPException(404, 'Deposit not found')
    payment = db.get(Payment, deposit.payment_id)
    phonepe.recheck(db, payment); sync(db, payment)
    if deposit.refund_id:
        phonepe.recheck_refund(db, deposit.refund_id)
        refund = db.get(Refund, deposit.refund_id)
        if refund.status == 'COMPLETED':
            deposit.status = 'REFUNDED'
            notice(db, driver_id, 'DEPOSIT_REFUNDED', f'Your security deposit of INR {deposit.amount} has been refunded.')
    return {'deposit_id': deposit.id, 'status': deposit.status}


def refund(db, driver_id, deposit_id):
    application = partner(db, driver_id, True)
    if application.account_status not in {'SUSPENDED', 'DEACTIVATED'}: raise HTTPException(409, 'Deactivate or suspend the driver before refunding the deposit')
    if db.scalar(select(Order.id).where(Order.driver_id == driver_id, Order.status.notin_(['DELIVERED', 'COMPLETED', 'CANCELLED', 'CANCELED', 'REJECTED']))): raise HTTPException(409, 'Resolve active deliveries before refunding the deposit')
    deposit = db.get(DriverDeposit, deposit_id)
    if not deposit or deposit.driver_id != driver_id: raise HTTPException(404, 'Deposit not found')
    if deposit.refund_id: return recheck(db, driver_id, deposit_id)
    payment = db.get(Payment, deposit.payment_id)
    result = phonepe.refund(db, payment, SimpleNamespace(request_key=f'driver-deposit:{deposit.id}', amount=payment.amount, reason='Refundable driver security deposit'))
    deposit.refund_id = result['id']; deposit.status = 'REFUND_PENDING'
    return {'deposit_id': deposit.id, 'refund_id': deposit.refund_id, 'status': deposit.status}
