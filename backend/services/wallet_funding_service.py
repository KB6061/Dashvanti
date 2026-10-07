import os
import secrets
from decimal import Decimal
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import User, Customer, now
from backend.customer_account_models import CustomerWallet, CustomerWalletTransaction
from backend.account_enhancement_models import WalletFunding
from backend.account_enhancement_models import WalletCheckout
import json
from backend.services.customer_account_service import currency, reauthenticate, stripe_request
from backend.services import account_gateway_service as gateways


def provider_request(method, url, **kwargs):
    try:
        response = httpx.request(method, url, timeout=15, **kwargs)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Payment provider could not complete the request')


def public_origin():
    value = os.environ.get('CUSTOMER_PUBLIC_ORIGIN', 'https://customer.dashvanti.com').rstrip('/')
    if not value.startswith('https://'):
        raise HTTPException(503, 'Configure an HTTPS customer origin')
    return value


def paypal_token(environment=None):
    base = 'https://api-m.paypal.com' if (environment or os.environ.get('PAYPAL_ENVIRONMENT')) == 'production' else 'https://api-m.sandbox.paypal.com'
    token = provider_request('POST', base + '/v1/oauth2/token',
                             auth=(os.environ['PAYPAL_CLIENT_ID'], os.environ['PAYPAL_CLIENT_SECRET']),
                             data={'grant_type': 'client_credentials'})['access_token']
    return base, {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}


def begin(db, user, data):
    gateways.require(db, user, data.gateway)
    db.scalar(select(Customer).where(Customer.id == user.id).with_for_update())
    key = str(user.id) + ':' + data.request_key
    row = db.scalar(select(WalletFunding).where(WalletFunding.request_key == key))
    curr, _ = currency(user)
    if row:
        if (row.amount, row.currency, row.provider) != (data.amount, curr, data.gateway):
            raise HTTPException(409, 'This request key belongs to a different payment')
        return {'id': row.id, 'redirect': row.checkout_url, 'status': row.status}
    row = WalletFunding(id=secrets.token_hex(16), customer_id=user.id, request_key=key,
                         provider=data.gateway, amount=data.amount, currency=curr)
    db.add(row)
    db.flush()
    success = public_origin() + '/customer/account/wallet?funding_id=' + row.id
    minor = int(row.amount * 100)
    if row.provider in {'stripe','apple_pay'} or row.provider=='google_pay' and curr!='INR':
        row.environment = 'production' if os.environ.get('STRIPE_SECRET_KEY','').startswith('sk_live_') else 'sandbox'
        session = stripe_request('POST', 'payment_intents', {'amount':str(minor),'currency':curr.lower(),
            'metadata[wallet_funding_id]':row.id,'payment_method_types[0]':'card'})
        enabled={item['name'] for item in gateways.methods(db,user)}
        row.provider_reference=session['id']
        row.checkout_url=public_origin()+'/customer/wallet-checkout/'+row.id
        db.add(WalletCheckout(funding_id=row.id,payload=json.dumps({'client_secret':session['client_secret'],
            'publishable_key':os.environ['STRIPE_PUBLISHABLE_KEY'],'apple_pay':'apple_pay' in enabled,
            'google_pay':'google_pay' in enabled,'return_url':success})))
    elif row.provider == 'cash_app':
        row.environment = 'production' if os.environ.get('STRIPE_SECRET_KEY','').startswith('sk_live_') else 'sandbox'
        session=stripe_request('POST','checkout/sessions',{'mode':'payment','client_reference_id':row.id,
            'metadata[wallet_funding_id]':row.id,'payment_method_types[0]':'cashapp',
            'line_items[0][price_data][currency]':'usd','line_items[0][price_data][unit_amount]':str(minor),
            'line_items[0][price_data][product_data][name]':'Dashvanti wallet credit','line_items[0][quantity]':'1',
            'success_url':success,'cancel_url':public_origin()+'/customer/account/wallet'})
        row.provider_reference,row.checkout_url=session['id'],session['url']
    elif row.provider == 'paypal':
        row.environment = 'production' if os.environ.get('PAYPAL_ENVIRONMENT') == 'production' else 'sandbox'
        base, headers = paypal_token(row.environment)
        headers['PayPal-Request-Id'] = row.id
        result = provider_request('POST', base + '/v2/checkout/orders', headers=headers, json={
            'intent': 'CAPTURE', 'purchase_units': [{'reference_id': row.id, 'custom_id': row.id,
                'amount': {'currency_code': curr, 'value': str(row.amount)}}],
            'application_context': {'return_url': success, 'cancel_url': public_origin() + '/customer/account/wallet'}})
        row.provider_reference = result['id']
        row.checkout_url = next(link['href'] for link in result['links'] if link['rel'] == 'approve')
    elif row.provider in {'razorpay','upi'} or row.provider=='google_pay' and curr=='INR':
        row.environment = 'production' if os.environ.get('RAZORPAY_KEY_ID','').startswith('rzp_live_') else 'sandbox'
        payload = {
                'amount': minor, 'currency': curr, 'reference_id': row.id, 'description': 'Dashvanti wallet credit',
                'callback_url': success, 'callback_method': 'get', 'notes': {'wallet_funding_id': row.id}}
        if row.provider in {'upi','google_pay'}:payload['upi_link']=True
        result = provider_request('POST', 'https://api.razorpay.com/v1/payment_links',
            auth=(os.environ['RAZORPAY_KEY_ID'], os.environ['RAZORPAY_KEY_SECRET']), json=payload)
        row.provider_reference, row.checkout_url = result['id'], result['short_url']
    elif row.provider == 'phonepe':
        from backend.services.admin_payment_service import active_settings
        from backend.services.phonepe_service import Gateway
        gateway = Gateway(active_settings(db))
        row.provider_settings_id = gateway.row.id
        row.environment = gateway.row.environment
        if gateway.row.api_version != 'v2':
            raise HTTPException(409, 'Wallet funding requires PhonePe v2 configuration')
        result = gateway.request('POST', '/checkout/v2/pay', {
            'merchantOrderId': row.id, 'amount': minor, 'expireAfter': 1200,
            'paymentFlow': {'type': 'PG_CHECKOUT', 'merchantUrls': {'redirectUrl': success}}})
        row.provider_reference, row.checkout_url = row.id, result['redirectUrl']
    else:
        from backend.services.wallet_provider_service import begin as provider_begin
        provider_begin(db,row,user,success)
    db.flush()
    if not row.checkout_url.startswith('https://'):
        raise HTTPException(502,'Payment provider did not return a secure checkout URL')
    return {'id': row.id, 'redirect': row.checkout_url, 'status': row.status}


def verified_payment(db, row):
    reference = quote(row.provider_reference, safe='')
    minor = int(row.amount * 100)
    if row.provider in {'stripe','apple_pay','google_pay'} and row.provider_reference.startswith('pi_'):
        result=stripe_request('GET','payment_intents/'+reference+'?expand[]=latest_charge')
        if result.get('metadata',{}).get('wallet_funding_id')!=row.id or result.get('amount')!=minor or result.get('currency','').upper()!=row.currency:
            raise HTTPException(409,'Payment reference or amount mismatch')
        if result.get('livemode') is not (row.environment=='production'):
            raise HTTPException(409,'Payment environment mismatch')
        if result.get('status')!='succeeded':return False,row.environment=='production'
        details=(result.get('latest_charge') or {}).get('payment_method_details',{})
        instrument=details.get('card',{}).get('wallet',{}).get('type') if details.get('card',{}).get('wallet') else None
        if row.provider in {'apple_pay','google_pay'} and instrument!=row.provider:
            raise HTTPException(409,'Payment instrument mismatch')
        return result.get('amount_received')==minor,row.environment=='production'
    if row.provider in {'stripe','cash_app'}:
        result = stripe_request('GET', 'checkout/sessions/' + reference)
        if result.get('client_reference_id') != row.id or result.get('amount_total') != minor or result.get('currency', '').upper() != row.currency:
            raise HTTPException(409, 'Payment reference or amount mismatch')
        if result.get('livemode') is not (row.environment=='production'):
            raise HTTPException(409, 'Payment environment mismatch')
        return result.get('payment_status') == 'paid', result.get('livemode') is True
    if row.provider == 'paypal':
        base, headers = paypal_token(row.environment)
        result = provider_request('GET', base + '/v2/checkout/orders/' + reference, headers=headers)
        if result.get('status') == 'APPROVED':
            headers['PayPal-Request-Id'] = row.id
            result = provider_request('POST', base + '/v2/checkout/orders/' + reference + '/capture', headers=headers, json={})
        units = result.get('purchase_units', [])
        if len(units) != 1 or units[0].get('custom_id') != row.id:
            raise HTTPException(409, 'Payment reference mismatch')
        captures = units[0].get('payments', {}).get('captures', [])
        paid = [item for item in captures if item.get('status') == 'COMPLETED']
        matched = len(paid) == 1 and paid[0]['amount']['currency_code'] == row.currency and Decimal(paid[0]['amount']['value']) == row.amount
        return result.get('status') == 'COMPLETED' and matched, row.environment == 'production'
    if row.provider in {'razorpay','upi'} or row.provider=='google_pay' and row.currency=='INR':
        result = provider_request('GET', 'https://api.razorpay.com/v1/payment_links/' + reference,
                                  auth=(os.environ['RAZORPAY_KEY_ID'], os.environ['RAZORPAY_KEY_SECRET']))
        if result.get('reference_id') != row.id or result.get('amount') != minor or result.get('currency') != row.currency:
            raise HTTPException(409, 'Payment amount or reference mismatch')
        if os.environ['RAZORPAY_KEY_ID'].startswith('rzp_live_') != (row.environment=='production'):
            raise HTTPException(409, 'Payment environment mismatch')
        return result.get('status') == 'paid' and result.get('amount_paid') == minor, row.environment=='production'
    if row.provider == 'phonepe':
        from backend.payment_models import AdminSettings
        from backend.services.phonepe_service import Gateway
        settings = db.get(AdminSettings,row.provider_settings_id)
        if not settings:
            raise HTTPException(409,'Original payment configuration is unavailable')
        gateway = Gateway(settings)
        result = gateway.request('GET', '/checkout/v2/order/' + reference + '/status')
        if result.get('amount') != minor:
            raise HTTPException(409, 'Payment amount mismatch')
        return result.get('state') == 'COMPLETED', gateway.row.environment == 'production'
    from backend.services.wallet_provider_service import verify
    return verify(db,row)


def complete(db, user, funding_id):
    row = db.scalar(select(WalletFunding).where(WalletFunding.id == funding_id).with_for_update())
    if not row or row.customer_id != user.id:
        raise HTTPException(404, 'Payment not found')
    if row.status in {'completed', 'test_complete'}:
        return {'status': row.status, 'message': 'Payment already verified'}
    succeeded, live = verified_payment(db, row)
    if not succeeded:
        return {'status': 'pending', 'message': 'Payment has not completed yet'}
    if not live:
        row.status = 'test_complete'
        row.completed_at = now()
        return {'status': row.status, 'message': 'Sandbox payment verified. Real wallet balance was not changed.'}
    db.scalar(select(Customer).where(Customer.id == user.id).with_for_update())
    wallet = db.get(CustomerWallet, (user.id, row.currency))
    if not wallet:
        wallet = CustomerWallet(customer_id=user.id, currency=row.currency, balance=Decimal(0))
        db.add(wallet)
    reference = 'funding:' + row.id
    if not db.scalar(select(CustomerWalletTransaction.id).where(CustomerWalletTransaction.reference == reference)):
        wallet.balance += row.amount
        db.add(CustomerWalletTransaction(customer_id=user.id, currency=row.currency, amount=row.amount,
                                         kind='add_money', reference=reference, description='Verified ' + row.provider + ' payment'))
    row.status, row.completed_at = 'completed', now()
    db.flush()
    return {'status': row.status, 'message': 'Wallet balance updated', 'balance': wallet.balance}


def transfer(db, user, data):
    reauthenticate(user, data.current_password)
    recipient = db.scalar(select(User).where(User.email == data.recipient_email.strip().lower(), User.role == 'customer'))
    if not recipient or recipient.id == user.id or recipient.country != user.country:
        raise HTTPException(422, 'Choose another customer using the same currency and country')
    curr, _ = currency(user)
    # Deterministic lock order prevents opposing transfers from deadlocking.
    list(db.scalars(select(Customer).where(Customer.id.in_([user.id, recipient.id])).order_by(Customer.id).with_for_update()))
    reference = 'transfer:' + str(user.id) + ':' + data.request_key
    previous = db.scalar(select(CustomerWalletTransaction).where(CustomerWalletTransaction.reference == reference + ':out'))
    if previous:
        if previous.amount != -data.amount or previous.description != 'Credits to customer ' + str(recipient.id):
            raise HTTPException(409, 'Request key already used for a different transfer')
        return {'message': 'Transfer already completed'}
    source = db.get(CustomerWallet, (user.id, curr))
    if not source or source.balance < data.amount:
        raise HTTPException(409, 'Insufficient wallet balance')
    target = db.get(CustomerWallet, (recipient.id, curr))
    if not target:
        target = CustomerWallet(customer_id=recipient.id, currency=curr, balance=Decimal(0))
        db.add(target)
    source.balance -= data.amount
    target.balance += data.amount
    db.add_all([
        CustomerWalletTransaction(customer_id=user.id, currency=curr, amount=-data.amount, kind='transfer_out', reference=reference + ':out', description='Credits to customer ' + str(recipient.id)),
        CustomerWalletTransaction(customer_id=recipient.id, currency=curr, amount=data.amount, kind='transfer_in', reference=reference + ':in', description='Credits from customer ' + str(user.id))])
    db.flush()
    return {'message': 'Credits transferred', 'balance': source.balance}


def refund_credit(db, user, currency_code, amount, refund_reference):
    """Call only after a verified refund intended for wallet credit, never alongside a gateway refund."""
    db.scalar(select(Customer).where(Customer.id == user.id).with_for_update())
    amount = Decimal(amount)
    if amount <= 0 or currency_code not in {'USD', 'INR'} or not refund_reference:
        raise HTTPException(422, 'Invalid refund credit')
    reference = 'wallet-refund:' + refund_reference
    if db.scalar(select(CustomerWalletTransaction.id).where(CustomerWalletTransaction.reference == reference)):
        return
    wallet = db.get(CustomerWallet, (user.id, currency_code))
    if not wallet:
        wallet = CustomerWallet(customer_id=user.id, currency=currency_code, balance=Decimal(0))
        db.add(wallet)
    wallet.balance += amount
    db.add(CustomerWalletTransaction(customer_id=user.id, currency=currency_code, amount=amount,
                                     kind='refund', reference=reference, description='Verified refund credit'))
