import hashlib
import hmac
import json
import os
import time
import base64
from urllib.parse import parse_qsl
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import User
from backend.account_enhancement_models import WalletFunding
from backend.services import wallet_funding_service as wallet


def payload(raw):
    if len(raw)>65536:
        raise HTTPException(413,'Webhook payload too large')
    try:
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError()
        return data
    except (ValueError,TypeError):
        raise HTTPException(400,'Invalid webhook payload')


async def read_body(request):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>65536:raise HTTPException(413,'Webhook payload too large')
    return bytes(raw)


def nested(data,*keys):
    for key in keys:
        if not isinstance(data,dict):return None
        data=data.get(key)
    return data


def phonepe_funding(db, raw, headers):
    data=payload(raw)
    reference=nested(data,'payload','merchantOrderId')
    if not isinstance(reference,str) or len(reference)>120:return None
    row=db.scalar(select(WalletFunding).where(WalletFunding.provider=='phonepe',WalletFunding.provider_reference==reference))
    if not row:return None
    from backend.payment_models import AdminSettings
    from backend.services.admin_payment_service import credentials
    from backend.utils.signature import verify_sha_webhook
    settings=db.get(AdminSettings,row.provider_settings_id)
    if not settings:raise HTTPException(409,'Payment settings unavailable')
    cfg=credentials(settings)
    if not verify_sha_webhook(headers.get('authorization',''),cfg.get('webhook_username'),cfg.get('webhook_password')):
        raise HTTPException(401,'Invalid PhonePe webhook signature')
    return wallet.complete(db,db.get(User,row.customer_id),row.id)


def receive(db, provider, raw, headers):
    if provider=='paytm':
        try:
            from paytmchecksum import PaytmChecksum
            data=dict(parse_qsl(raw.decode('utf-8'),max_num_fields=50,strict_parsing=True))
            signature=data.pop('CHECKSUMHASH','')
            key=os.environ.get('PAYTM_MERCHANT_KEY','')
            if not key or not PaytmChecksum.verifySignature(data,key,signature):raise ValueError()
        except (ImportError,ValueError,UnicodeError):raise HTTPException(401,'Invalid Paytm callback signature')
        row=db.scalar(select(WalletFunding).where(WalletFunding.provider=='paytm',WalletFunding.provider_reference==data.get('ORDERID','')))
        if not row:raise HTTPException(404,'Wallet payment not found')
        return {'received':True,**wallet.complete(db,db.get(User,row.customer_id),row.id)}
    data=payload(raw)
    if provider=='stripe':
        secret=os.environ.get('STRIPE_WALLET_WEBHOOK_SECRET','')
        parts=[part.split('=',1) for part in headers.get('stripe-signature','').split(',') if '=' in part]
        timestamp=next((value for key,value in parts if key=='t'),'')
        try:fresh=abs(time.time()-int(timestamp))<=300
        except ValueError:fresh=False
        digest=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if not secret or not fresh or not any(key=='v1' and hmac.compare_digest(value,digest) for key,value in parts):
            raise HTTPException(401,'Invalid Stripe webhook signature')
        reference=nested(data,'data','object','metadata','wallet_funding_id') or nested(data,'data','object','client_reference_id')
        if reference and (not isinstance(reference,str) or len(reference)>120):raise HTTPException(400,'Invalid payment reference')
        row=db.get(WalletFunding,reference) if reference else None
    elif provider=='razorpay':
        secret=os.environ.get('RAZORPAY_WALLET_WEBHOOK_SECRET','')
        signature=headers.get('x-razorpay-signature','')
        if not secret or not hmac.compare_digest(hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest(),signature):
            raise HTTPException(401,'Invalid Razorpay webhook signature')
        reference=nested(data,'payload','payment_link','entity','reference_id')
        if reference and (not isinstance(reference,str) or len(reference)>120):raise HTTPException(400,'Invalid payment reference')
        row=db.get(WalletFunding,reference) if reference else None
    elif provider=='paypal':
        reference=nested(data,'resource','supplementary_data','related_ids','order_id') or nested(data,'resource','id')
        if not isinstance(reference,str) or len(reference)>120:return {'received':True}
        row=db.scalar(select(WalletFunding).where(WalletFunding.provider=='paypal',WalletFunding.provider_reference==reference))
        if not row:return {'received':True}
        webhook_id=os.environ.get('PAYPAL_WALLET_WEBHOOK_ID','')
        if not webhook_id:raise HTTPException(503,'PayPal webhook verification is not configured')
        base,auth=wallet.paypal_token(row.environment)
        result=wallet.provider_request('POST',base+'/v1/notifications/verify-webhook-signature',headers=auth,json={
            'auth_algo':headers.get('paypal-auth-algo'),'cert_url':headers.get('paypal-cert-url'),
            'transmission_id':headers.get('paypal-transmission-id'),'transmission_sig':headers.get('paypal-transmission-sig'),
            'transmission_time':headers.get('paypal-transmission-time'),'webhook_id':webhook_id,'webhook_event':data})
        if result.get('verification_status')!='SUCCESS':raise HTTPException(401,'Invalid PayPal webhook signature')
    elif provider=='phonepe':
        result=phonepe_funding(db,raw,headers)
        if result is None:raise HTTPException(404,'Wallet payment not found')
        return {'received':True,**result}
    elif provider=='square':
        secret=os.environ.get('SQUARE_WALLET_WEBHOOK_SECRET','')
        url=os.environ.get('SQUARE_WALLET_WEBHOOK_URL','')
        signature=base64.b64encode(hmac.new(secret.encode(),url.encode()+raw,hashlib.sha256).digest()).decode()
        if not secret or not url or not hmac.compare_digest(signature,headers.get('x-square-hmacsha256-signature','')):
            raise HTTPException(401,'Invalid Square webhook signature')
        reference=nested(data,'data','object','payment','order_id')
        row=db.scalar(select(WalletFunding).where(WalletFunding.provider=='square',WalletFunding.provider_reference==reference)) if isinstance(reference,str) else None
    elif provider=='authorize_net':
        secret=os.environ.get('AUTHORIZE_NET_SIGNATURE_KEY','')
        try:signing_key=bytes.fromhex(secret)
        except ValueError:signing_key=b''
        signature='sha512='+hmac.new(signing_key,raw,hashlib.sha512).hexdigest()
        if not signing_key or not hmac.compare_digest(signature.lower(),headers.get('x-anet-signature','').lower()):
            raise HTTPException(401,'Invalid Authorize.Net webhook signature')
        transaction_id=nested(data,'payload','id')
        if not isinstance(transaction_id,str) or not transaction_id.isdigit():return {'received':True}
        from types import SimpleNamespace
        from backend.services.wallet_provider_service import authorize
        environment='production' if os.environ.get('AUTHORIZE_NET_ENVIRONMENT')=='production' else 'sandbox'
        transaction=authorize(SimpleNamespace(environment=environment),'getTransactionDetailsRequest',{'transId':transaction_id})['transaction']
        invoice=transaction.get('order',{}).get('invoiceNumber')
        row=db.scalar(select(WalletFunding).where(WalletFunding.provider=='authorize_net',WalletFunding.provider_reference==invoice).with_for_update()) if isinstance(invoice,str) else None
        if row:
            from backend.account_enhancement_models import WalletCheckout
            checkout=db.get(WalletCheckout,row.id)
            if row.environment!=environment or not checkout:raise HTTPException(409,'Checkout environment mismatch')
            if checkout.payment_reference and checkout.payment_reference!=transaction_id:raise HTTPException(409,'Checkout transaction mismatch')
            checkout.payment_reference=transaction_id
    else:raise HTTPException(404,'Webhook provider not found')
    if not row:return {'received':True}
    aliases={'stripe':{'stripe','cash_app','apple_pay','google_pay'},'razorpay':{'razorpay','upi','google_pay'}}
    if row.provider not in aliases.get(provider,{provider}):raise HTTPException(409,'Webhook provider mismatch')
    return {'received':True,**wallet.complete(db,db.get(User,row.customer_id),row.id)}
