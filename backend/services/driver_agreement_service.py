import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
import unicodedata
import uuid
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import now
from backend.models_driver_agreement import DriverAgreementAcceptance
from backend.services import driver_agreement_terms as terms

AGREEMENT_HASH = hashlib.sha256(json.dumps([terms.VERSION, terms.SECTIONS, terms.ACKNOWLEDGEMENTS], ensure_ascii=False).encode()).hexdigest()


def payload():
    return {'title': terms.TITLE, 'agreement_version': terms.VERSION, 'agreement_hash': AGREEMENT_HASH,
            'sections': [{'title': title, 'text': text} for title, text in terms.SECTIONS],
            'acknowledgements': [{'key': key, 'text': text} for key, text in terms.ACKNOWLEDGEMENTS], 'statement': terms.STATEMENT}


def start(db, user=None):
    token = secrets.token_urlsafe(48)
    row = DriverAgreementAcceptance(driver_temp_id=str(uuid.uuid4()), driver_id=user.id if user else None,
        agreement_version=terms.VERSION, agreement_hash=AGREEMENT_HASH, agreement_content=json.dumps(payload(), ensure_ascii=False), token_digest=hashlib.sha256(token.encode()).hexdigest(), expires_at=now()+timedelta(hours=24))
    db.add(row); db.flush()
    return {**payload(), 'token': token, 'driver_temp_id': row.driver_temp_id}


def session(db, token, user=None, lock=False):
    if not token or len(token) > 200: raise HTTPException(403, 'Read and accept the Driver Partner Agreement before continuing.')
    query = select(DriverAgreementAcceptance).where(DriverAgreementAcceptance.token_digest == hashlib.sha256(token.encode()).hexdigest())
    row = db.scalar(query.with_for_update() if lock else query)
    if not row or row.agreement_version != terms.VERSION or row.agreement_hash != AGREEMENT_HASH or row.cancelled_at or row.expires_at <= now():
        raise HTTPException(403, 'Agreement session expired. Please read and accept the current agreement.')
    if row.driver_id is not None and (not user or user.role != 'driver' or user.id != row.driver_id):
        raise HTTPException(403, 'This agreement session belongs to another driver.')
    if row.registered_at: raise HTTPException(403, 'Agreement session has already been used for registration.')
    return row


def accepted_for_driver(db, driver_id):
    return db.scalar(select(DriverAgreementAcceptance).where(DriverAgreementAcceptance.driver_id == driver_id,
        DriverAgreementAcceptance.agreement_version == terms.VERSION, DriverAgreementAcceptance.agreement_hash == AGREEMENT_HASH,
        DriverAgreementAcceptance.accepted.is_(True), DriverAgreementAcceptance.cancelled_at.is_(None)).order_by(DriverAgreementAcceptance.id.desc()))


def require_accepted(db, driver_id):
    row = accepted_for_driver(db, driver_id)
    if not row: raise HTTPException(403, 'Read and accept the Driver Partner Agreement before accessing onboarding.')
    return row


def status(db, token=None, user=None):
    row = accepted_for_driver(db, user.id) if user else None
    if not row:
        try: row = session(db, token, user)
        except HTTPException: return {'accepted': False, 'agreement_version': terms.VERSION}
    return {'accepted': row.accepted, 'agreement_version': row.agreement_version, 'full_legal_name': row.full_legal_name, 'accepted_at': row.accepted_at}


def record_read(db, token, data, user=None):
    row = session(db, token, user, True)
    if data.agreement_version != terms.VERSION or data.scroll_completed is not True:
        raise HTTPException(422, 'Scroll to the bottom of the current agreement.')
    if not row.accepted and not row.scroll_completed_at: row.scroll_completed_at = now()
    return {'scroll_completed': True}


def request_context(request):
    address = request.client.host if request.client else ''
    browser = request.headers.get('user-agent', '')[:1024]
    platform = request.headers.get('sec-ch-ua-platform', '')[:200]
    mobile = request.headers.get('sec-ch-ua-mobile', '')[:10]
    key = os.getenv('DRIVER_AGREEMENT_PROXY_SECRET', '')
    stamp = request.headers.get('x-dashvanti-consent-time', '')
    forwarded = request.headers.get('x-dashvanti-consent-ip', '')
    forwarded_browser = request.headers.get('x-dashvanti-consent-browser', '')[:1024]
    forwarded_device = request.headers.get('x-dashvanti-consent-device', '')[:250]
    signature = request.headers.get('x-dashvanti-consent-signature', '')
    if key and stamp:
        try:
            valid = abs(time.time()-int(stamp)) <= 60 and hmac.compare_digest(signature, hmac.new(key.encode(), f'{stamp}:{forwarded}:{forwarded_browser}:{forwarded_device}'.encode(), hashlib.sha256).hexdigest())
        except ValueError: valid = False
        if valid: address, browser, platform, mobile = forwarded, forwarded_browser, forwarded_device, ''
    try: address = str(ipaddress.ip_address(address))
    except ValueError: address = ''
    return {'ip_address': address, 'browser_information': browser, 'device_information': json.dumps({'platform': platform, 'mobile': mobile, 'user_agent': browser})}


def accept(db, token, data, context, user=None):
    row = session(db, token, user, True)
    required = {key for key, _ in terms.ACKNOWLEDGEMENTS}
    if data.agreement_version != terms.VERSION or not row.scroll_completed_at:
        raise HTTPException(422, 'Read the complete current agreement before accepting.')
    if set(data.acknowledgements) != required or not all(value is True for value in data.acknowledgements.values()):
        raise HTTPException(422, 'Accept every required acknowledgement.')
    if row.accepted:
        if row.full_legal_name != data.full_legal_name: raise HTTPException(409, 'Acceptance is already recorded with a different legal name.')
    else:
        row.full_legal_name = data.full_legal_name
        row.accepted = True
        row.accepted_at = row.acceptance_timestamp = now()
        row.acknowledgements = json.dumps(sorted(required))
        for key, value in context.items(): setattr(row, key, value)
        if user: row.driver_id = user.id
    return {'accepted': True, 'agreement_version': row.agreement_version, 'message': terms.SUCCESS, 'accepted_at': row.accepted_at}


def decline(db, token, user=None):
    try: row = session(db, token, user, True)
    except HTTPException: return {'cancelled': True}
    row.cancelled_at = now()
    return {'cancelled': True}


def registration_consent(db, data):
    row = session(db, getattr(data, 'driver_agreement_token', None), lock=True)
    if not row.accepted: raise HTTPException(403, 'Accept the Driver Partner Agreement before creating a driver account.')
    normalise = lambda value: unicodedata.normalize('NFKC', ' '.join(value.split())).casefold()
    if normalise(data.name) != normalise(row.full_legal_name):
        raise HTTPException(422, 'Account name must match the full legal name recorded in your agreement.')
    return row
