import json
import os
from decimal import Decimal
from urllib.parse import quote
from fastapi import HTTPException
from backend.account_enhancement_models import WalletCheckout


def request(method, url, **kwargs):
    from backend.services.wallet_funding_service import provider_request
    return provider_request(method, url, **kwargs)


def origin():
    from backend.services.wallet_funding_service import public_origin
    return public_origin()


def square(row):
    base = 'https://connect.squareup.com' if row.environment == 'production' else 'https://connect.squareupsandbox.com'
    return base, {'Authorization': 'Bearer '+os.environ['SQUARE_ACCESS_TOKEN'], 'Content-Type': 'application/json'}


def authorize(row, action, body):
    base = 'https://api.authorize.net' if row.environment == 'production' else 'https://apitest.authorize.net'
    result = request('POST', base+'/xml/v1/request.api', json={action: {
        'merchantAuthentication': {'name': os.environ['AUTHORIZE_NET_LOGIN_ID'], 'transactionKey': os.environ['AUTHORIZE_NET_TRANSACTION_KEY']}, **body}})
    if result.get('messages', {}).get('resultCode') != 'Ok':
        raise HTTPException(502, 'Authorize.Net could not complete this request')
    return result


def paytm(row, path, body, query=None):
    try:
        from paytmchecksum import PaytmChecksum
    except ImportError:
        raise HTTPException(503, 'Paytm checksum dependency is not installed')
    base = 'https://securegw.paytm.in' if row.environment == 'production' else 'https://securegw-stage.paytm.in'
    value = json.dumps(body, separators=(',', ':'))
    result = request('POST', base+path, params=query, json={'body': body, 'head': {
        'signature': PaytmChecksum.generateSignature(value, os.environ['PAYTM_MERCHANT_KEY'])}})
    response_body = result.get('body', {})
    signature = result.get('head', {}).get('signature')
    if not signature or not PaytmChecksum.verifySignature(json.dumps(response_body, separators=(',', ':')), os.environ['PAYTM_MERCHANT_KEY'], signature):
        raise HTTPException(502, 'Invalid Paytm response signature')
    return base, response_body


def begin(db, row, user, success):
    minor = int(row.amount*100)
    if row.provider == 'square':
        if row.currency != 'USD':raise HTTPException(409, 'Square funding requires USD')
        row.environment = 'production' if os.environ.get('SQUARE_ENVIRONMENT') == 'production' else 'sandbox'
        base, headers = square(row)
        from backend.services.account_gateway_service import methods
        enabled={item['name'] for item in methods(db,user)}
        result = request('POST', base+'/v2/online-checkout/payment-links', headers=headers, json={
            'idempotency_key': row.id, 'order': {'location_id': os.environ['SQUARE_LOCATION_ID'], 'reference_id': row.id,
            'line_items': [{'name': 'Dashvanti wallet credit', 'quantity': '1', 'base_price_money': {'amount': minor, 'currency': row.currency}}]},
            'checkout_options': {'redirect_url': success, 'allow_tipping': False,'accepted_payment_methods':{
                'apple_pay':'apple_pay' in enabled,'google_pay':'google_pay' in enabled,'cash_app_pay':'cash_app' in enabled,'afterpay_clearpay':False}}})
        row.provider_reference = result['payment_link']['order_id']
        row.checkout_url = result['payment_link']['url']
    elif row.provider == 'authorize_net':
        if row.currency != 'USD':raise HTTPException(409, 'Authorize.Net funding requires USD')
        row.environment = 'production' if os.environ.get('AUTHORIZE_NET_ENVIRONMENT') == 'production' else 'sandbox'
        invoice = row.id[:20]
        result = authorize(row, 'getHostedPaymentPageRequest', {
            'refId': invoice, 'transactionRequest': {'transactionType': 'authCaptureTransaction', 'amount': str(row.amount),
                'order': {'invoiceNumber': invoice, 'description': 'Dashvanti wallet credit'}, 'customer': {'id': str(user.id), 'email': user.email}},
            'hostedPaymentSettings': {'setting': [
                {'settingName': 'hostedPaymentReturnOptions', 'settingValue': json.dumps({'showReceipt': True, 'url': success, 'cancelUrl': origin()+'/customer/account/wallet'})},
                {'settingName': 'hostedPaymentPaymentOptions', 'settingValue': json.dumps({'showCreditCard': True, 'showBankAccount': False})}]}})
        row.provider_reference = invoice
        db.add(WalletCheckout(funding_id=row.id, payload=json.dumps({'token': result['token'], 'action':
            'https://accept.authorize.net/payment/payment' if row.environment == 'production' else 'https://test.authorize.net/payment/payment'})))
        row.checkout_url = origin()+'/customer/wallet-checkout/'+row.id
    elif row.provider == 'paytm':
        if row.currency != 'INR':raise HTTPException(409, 'Paytm funding requires INR')
        row.environment = 'production' if os.environ.get('PAYTM_ENVIRONMENT') == 'production' else 'sandbox'
        mid = os.environ['PAYTM_MERCHANT_ID']
        base, result = paytm(row, '/theia/api/v1/initiateTransaction', {
            'requestType': 'Payment', 'mid': mid, 'orderId': row.id,
            'websiteName': 'DEFAULT' if row.environment == 'production' else 'WEBSTAGING',
            'callbackUrl': origin()+'/customer/wallet-webhook/paytm',
            'txnAmount': {'value': str(row.amount), 'currency': 'INR'}, 'userInfo': {'custId': str(user.id), 'email': user.email}},
            {'mid': mid, 'orderId': row.id})
        if not result.get('txnToken'):raise HTTPException(502, 'Paytm did not create a checkout token')
        row.provider_reference = row.id
        db.add(WalletCheckout(funding_id=row.id, payload=json.dumps({'mid': mid, 'token': result['txnToken'], 'base': base})))
        row.checkout_url = origin()+'/customer/wallet-checkout/'+row.id
    else:
        raise HTTPException(409, 'Unsupported funding provider')


def verify(db, row):
    minor = int(row.amount*100)
    if row.provider == 'square':
        expected = 'production' if os.environ.get('SQUARE_ENVIRONMENT') == 'production' else 'sandbox'
        if expected != row.environment:raise HTTPException(409, 'Payment environment mismatch')
        base, headers = square(row)
        order = request('GET', base+'/v2/orders/'+quote(row.provider_reference, safe=''), headers=headers)['order']
        total = order.get('total_money', {})
        if order.get('reference_id') != row.id or total != {'amount': minor, 'currency': row.currency}:
            raise HTTPException(409, 'Payment reference or amount mismatch')
        tenders = order.get('tenders', [])
        if not tenders:return False, row.environment == 'production'
        if len(tenders) != 1:raise HTTPException(409, 'Unexpected payment tender count')
        payment = request('GET', base+'/v2/payments/'+quote(tenders[0]['payment_id'], safe=''), headers=headers)['payment']
        if payment.get('order_id') != row.provider_reference or payment.get('amount_money') != total:
            raise HTTPException(409, 'Payment amount or reference mismatch')
        return payment.get('status') == 'COMPLETED', row.environment == 'production'
    if row.provider == 'authorize_net':
        checkout = db.get(WalletCheckout, row.id)
        if not checkout or not checkout.payment_reference:return False, row.environment == 'production'
        transaction = authorize(row, 'getTransactionDetailsRequest', {'transId': checkout.payment_reference})['transaction']
        if (transaction.get('order', {}).get('invoiceNumber') != row.provider_reference or
                transaction.get('customer', {}).get('id') != str(row.customer_id) or Decimal(str(transaction.get('authAmount', 0))) != row.amount):
            raise HTTPException(409, 'Payment amount or reference mismatch')
        return transaction.get('transactionStatus') in {'capturedPendingSettlement', 'settledSuccessfully'}, row.environment == 'production'
    if row.provider == 'paytm':
        expected = 'production' if os.environ.get('PAYTM_ENVIRONMENT') == 'production' else 'sandbox'
        if expected != row.environment:raise HTTPException(409, 'Payment environment mismatch')
        _, result = paytm(row, '/v3/order/status', {'mid': os.environ['PAYTM_MERCHANT_ID'], 'orderId': row.provider_reference})
        if result.get('orderId') != row.provider_reference or Decimal(str(result.get('txnAmount', 0))) != row.amount:
            raise HTTPException(409, 'Payment amount or reference mismatch')
        return result.get('resultInfo', {}).get('resultStatus') == 'TXN_SUCCESS', row.environment == 'production'
    raise HTTPException(409, 'Unsupported funding provider')


def checkout(db, user, funding_id):
    from backend.account_enhancement_models import WalletFunding
    row = db.get(WalletFunding, funding_id)
    data = db.get(WalletCheckout, funding_id)
    if not row or row.customer_id != user.id or not data:raise HTTPException(404, 'Checkout not found')
    if row.status != 'pending':raise HTTPException(409, 'Checkout already completed')
    return {'id': row.id, 'provider': row.provider, 'amount': str(row.amount), 'currency': row.currency, **json.loads(data.payload)}
