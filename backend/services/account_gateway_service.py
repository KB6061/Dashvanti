import os
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import now
from backend.account_enhancement_models import GatewayControl

GATEWAYS = ('stripe', 'paypal', 'square', 'authorize_net', 'razorpay', 'cash_app', 'apple_pay', 'google_pay', 'upi', 'phonepe', 'paytm')
INDIA_ONLY = {'razorpay', 'upi', 'phonepe', 'paytm'}
WALLET_PROVIDERS = set(GATEWAYS)


def configured(db, name):
    if name == 'stripe':
        return bool(os.environ.get('STRIPE_SECRET_KEY') and os.environ.get('STRIPE_PUBLISHABLE_KEY'))
    if name == 'paypal':
        return bool(os.environ.get('PAYPAL_CLIENT_ID') and os.environ.get('PAYPAL_CLIENT_SECRET'))
    if name == 'razorpay':
        return bool(os.environ.get('RAZORPAY_KEY_ID') and os.environ.get('RAZORPAY_KEY_SECRET'))
    if name == 'phonepe':
        from backend.services.admin_payment_service import active_settings, configured as phonepe_configured
        row = active_settings(db)
        try:
            return bool(row and phonepe_configured(row))
        except HTTPException:
            return False
    # Alternative payment instruments must also be enabled in their gateway account.
    if name=='google_pay':
        return configured(db,'stripe') or configured(db,'razorpay')
    if name in {'apple_pay', 'cash_app'}:
        return configured(db, 'stripe')
    if name == 'upi':
        return configured(db, 'razorpay')
    if name == 'square':
        return bool(os.environ.get('SQUARE_ACCESS_TOKEN') and os.environ.get('SQUARE_LOCATION_ID'))
    if name == 'authorize_net':
        return bool(os.environ.get('AUTHORIZE_NET_LOGIN_ID') and os.environ.get('AUTHORIZE_NET_TRANSACTION_KEY') and os.environ.get('AUTHORIZE_NET_SIGNATURE_KEY'))
    if name == 'paytm':
        return bool(os.environ.get('PAYTM_MERCHANT_ID') and os.environ.get('PAYTM_MERCHANT_KEY'))
    return False


def methods(db, user=None, admin=False):
    controls = {row.name: row for row in db.scalars(select(GatewayControl))}
    result = []
    for name in GATEWAYS:
        row = controls.get(name)
        enabled = bool(row and row.enabled)
        country_allowed = bool(user and user.country in (row.countries.split(',') if row else []))
        if name in INDIA_ONLY and user and user.country != 'IN':
            country_allowed = False
        if name in {'square', 'authorize_net', 'cash_app','paypal'} and user and user.country != 'US':
            country_allowed = False
        if name=='apple_pay' and user and user.country == 'IN':
            country_allowed = False
        ready = configured(db, name)
        if name=='google_pay' and user:
            ready=configured(db,'razorpay') if user.country=='IN' else configured(db,'stripe')
        if admin or enabled and ready and country_allowed:
            result.append({'name': name, 'enabled': enabled, 'configured': ready,
                           'countries': row.countries.split(',') if row else ['IN'] if name in INDIA_ONLY else ['US', 'IN'],
                           'wallet_supported': name in WALLET_PROVIDERS})
    return result


def require(db, user, name):
    if name not in {item['name'] for item in methods(db, user)}:
        raise HTTPException(409, 'This payment gateway is not available for your account')
    if name not in WALLET_PROVIDERS:
        raise HTTPException(409, 'Choose a supported wallet funding gateway')


def update(db, user, data):
    from backend.services.incident_service import permission
    permission(db, user, 'gateway_edit')
    if data.name not in GATEWAYS:
        raise HTTPException(422, 'Unknown gateway')
    if data.name in INDIA_ONLY and set(data.countries) != {'IN'}:
        raise HTTPException(422, 'This gateway is available only in India')
    if not data.countries:
        raise HTTPException(422, 'Select at least one country')
    row = db.get(GatewayControl, data.name)
    if not row:
        row = GatewayControl(name=data.name)
        db.add(row)
    row.enabled = data.enabled
    row.countries = ','.join(sorted(set(data.countries)))
    row.updated_at = now()
    db.info['audit_reason'] = data.reason
    if data.name == 'phonepe':
        from backend.payment_models import PaymentMethod
        existing = db.get(PaymentMethod, 'phonepe')
        if existing:
            existing.enabled = data.enabled
    return {'message': 'Gateway visibility saved', 'configured': configured(db, data.name)}
