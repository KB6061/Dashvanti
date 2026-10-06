import json
import uuid
import re
from decimal import Decimal
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import AuditEvent, Order, PayoutTransaction, SystemConfig, User, now
from backend.services.admin_payment_service import cipher
from backend.services.finance_service import breakdown, money, terms

RESERVED = {'PAID', 'TRANSFERRED', 'PENDING', 'UNKNOWN', 'REVIEW_REQUIRED'}


def configuration(db, key=None):
    pointer=db.get(SystemConfig, 'payout:settings')
    if key is None:
        key=pointer.value if pointer else None
    row=db.get(SystemConfig, key) if key else None
    return (json.loads(cipher().decrypt(row.value.encode())) if row else
            {'manual_enabled':True,'automated_enabled':False,'environment':'test','secret_key':''}), key


def settings_view(db):
    cfg,_=configuration(db)
    recipients=[]
    prefix=f"payout:recipient:{cfg['environment']}:"
    for row in db.scalars(select(SystemConfig).where(SystemConfig.key.like(prefix+'%'))):
        user=db.get(User,int(row.key[len(prefix):]))
        if user: recipients.append({'user_id':user.id,'name':user.name,'role':user.role,'account_id':row.value})
    return {k:v for k,v in cfg.items() if k!='secret_key'} | {'configured':bool(cfg['secret_key']),'recipients':recipients}


def save_settings(db, data):
    cfg,_=configuration(db)
    value=data.model_dump()
    if value['environment']=='live' and not value.pop('confirm_live'):
        raise HTTPException(400,'Confirm live payouts explicitly')
    value.pop('confirm_live',None)
    value['secret_key']=value['secret_key'].strip() or (cfg['secret_key'] if cfg['environment']==value['environment'] else '')
    prefix='sk_live_' if value['environment']=='live' else 'sk_test_'
    if value['secret_key'] and not value['secret_key'].startswith(prefix):
        raise HTTPException(422,'Stripe key does not match the selected environment')
    if value['automated_enabled'] and not value['secret_key']:
        raise HTTPException(422,'Configure a Stripe secret key before enabling automated payouts')
    key='payout:settings:'+uuid.uuid4().hex
    db.add(SystemConfig(key=key,value=cipher().encrypt(json.dumps(value).encode()).decode()))
    pointer=db.get(SystemConfig,'payout:settings')
    if pointer: pointer.value=key
    else: db.add(SystemConfig(key='payout:settings',value=key))
    db.add(AuditEvent(action='payout-settings-updated',target='payouts',details=json.dumps({k:v for k,v in value.items() if k!='secret_key'})))
    db.flush()
    return settings_view(db)


def stripe(cfg, method, path, data=None, reference=None):
    headers={'Authorization':'Bearer '+cfg['secret_key']}
    if reference: headers['Idempotency-Key']=reference
    try:
        response=httpx.request(method,'https://api.stripe.com/v1/'+path,headers=headers,data=data,timeout=20)
    except httpx.HTTPError as exc:
        raise HTTPException(503,'Stripe response uncertain. Re-check this receipt before attempting another payout.') from exc
    try:
        payload=response.json()
    except ValueError as exc:
        raise HTTPException(503,'Invalid provider response. Re-check this receipt.') from exc
    if response.is_error:
        status=400 if response.status_code in {400,401,403,404,402} else 503
        message=re.sub(r'sk_(?:test|live)_\S+','[redacted]',str(payload.get('error',{}).get('message','Provider error')))
        raise HTTPException(status,'Stripe rejected the request: '+message[:300])
    return payload


def save_recipient(db, data):
    user=db.get(User,data.user_id)
    if not user or user.role not in {'driver','restaurant'}:
        raise HTTPException(404,'Driver or restaurant not found')
    cfg,_=configuration(db)
    if not cfg['secret_key']: raise HTTPException(409,'Configure Stripe first')
    account=stripe(cfg,'GET','accounts/'+data.account_id)
    if not account.get('payouts_enabled') or account.get('capabilities',{}).get('transfers')!='active':
        raise HTTPException(409,'Recipient must complete Stripe onboarding and enable transfers/payouts')
    key=f"payout:recipient:{cfg['environment']}:{user.id}"
    row=db.get(SystemConfig,key)
    if row: row.value=data.account_id
    else: db.add(SystemConfig(key=key,value=data.account_id))
    db.add(AuditEvent(action='payout-recipient-updated',target=f'user:{user.id}',details=data.account_id))
    return {'user_id':user.id,'account_id':data.account_id}


def metadata(db, row):
    record=db.get(SystemConfig,'payout:receipt:'+row.reference)
    return json.loads(record.value) if record else {}


def receipt(db, row):
    details=metadata(db,row)
    order=db.get(Order,row.order_id)
    user=db.get(User,row.payee_id)
    return {'id':row.id,'order_id':row.order_id,'payee_id':row.payee_id,'payee_name':user.name if user else '',
            'payee_role':row.payee_role,'amount':money(row.amount),'currency':order.currency if order else 'USD','status':row.status,
            'method':row.method,'reference':row.reference,'confirmation':details.get('confirmation',''),
            'provider_reference':details.get('provider_reference',''),'environment':details.get('environment','live'),
            'created_at':row.created_at,'paid_at':row.paid_at,'error':details.get('error','')}


def send(db, data):
    cfg,settings_key=configuration(db)
    if not cfg['manual_enabled'] and data.mode=='manual': raise HTTPException(409,'Manual payouts disabled by admin')
    if data.mode=='stripe' and (not cfg['automated_enabled'] or not cfg['secret_key']):
        raise HTTPException(409,'Automated payouts are not configured or enabled')
    if data.mode=='manual' and len(data.confirmation.strip())<3:
        raise HTTPException(422,'Enter the bank/payment confirmation number for the completed manual transfer')
    order=db.scalar(select(Order).where(Order.id==data.order_id).with_for_update().execution_options(populate_existing=True))
    if not order: raise HTTPException(404,'Order not found')
    if order.currency!='USD' or order.status not in {'DELIVERED','COMPLETED'}:
        raise HTTPException(409,'Payouts require a completed USD order')
    from backend.services.revenue_service import refund_map
    amounts=breakdown(order,refund_map(db).get(order.id,0),terms(db,order))
    payee=order.driver_id if data.payee_role=='driver' else order.restaurant_id
    due=amounts[data.payee_role+'_payout']
    previous=list(db.scalars(select(PayoutTransaction).where(PayoutTransaction.order_id==order.id,PayoutTransaction.payee_role==data.payee_role)))
    reserved=sum((money(row.amount) for row in previous if row.status in RESERVED),Decimal(0))
    pending=next((row for row in previous if row.status in {'PENDING','UNKNOWN'}),None)
    if pending: raise HTTPException(409,'A payout is already processing. Re-check receipt '+pending.reference)
    amount=money(due-reserved)
    if not payee or amount<=0: raise HTTPException(409,'No remaining payable balance')
    if amount!=data.expected_amount: raise HTTPException(409,'Balance changed. Refresh and review the payout amount')
    recipient=db.get(SystemConfig,f"payout:recipient:{cfg['environment']}:{payee}") if data.mode=='stripe' else None
    if data.mode=='stripe' and not recipient: raise HTTPException(409,'Configure the recipient Stripe connected account first')
    row=PayoutTransaction(order_id=order.id,payee_role=data.payee_role,payee_id=payee,amount=amount,
                          status='PAID' if data.mode=='manual' else 'PENDING',method='MANUAL' if data.mode=='manual' else 'STRIPE_CONNECT',
                          reference='DV-'+uuid.uuid4().hex.upper(),paid_at=now() if data.mode=='manual' else None)
    details={'confirmation':data.confirmation.strip() if data.mode=='manual' else '', 'settings_key':settings_key,
             'account_id':recipient.value if recipient else None,'environment':cfg['environment'] if recipient else 'live'}
    db.add(row)
    db.add(SystemConfig(key='payout:receipt:'+row.reference,value=json.dumps(details)))
    db.add(AuditEvent(action='payout-created',target=f'order:{order.id}:{data.payee_role}',details=row.reference))
    db.commit()
    return reconcile(db,row.id) if data.mode=='stripe' else receipt(db,row)


def reconcile(db, payout_id):
    row=db.scalar(select(PayoutTransaction).where(PayoutTransaction.id==payout_id).with_for_update().execution_options(populate_existing=True))
    if not row: raise HTTPException(404,'Payout not found')
    if row.method!='STRIPE_CONNECT': return receipt(db,row)
    details=metadata(db,row)
    cfg,_=configuration(db,details['settings_key'])
    try:
        if details.get('provider_reference'):
            transfer=stripe(cfg,'GET','transfers/'+details['provider_reference'])
        else:
            transfer=stripe(cfg,'POST','transfers',{'amount':int(row.amount*100),'currency':'usd',
                'destination':details['account_id'],'transfer_group':'ORDER_'+str(row.order_id),
                'metadata[receipt]':row.reference,'metadata[order_id]':row.order_id},row.reference)
        if transfer.get('amount')!=int(row.amount*100) or transfer.get('currency')!='usd' or transfer.get('destination')!=details['account_id'] or bool(transfer.get('livemode'))!=(cfg['environment']=='live'):
            raise HTTPException(503,'Provider transfer details do not match this payout')
        details['provider_reference']=transfer['id']
        if transfer.get('amount_reversed',0):
            row.status='REVIEW_REQUIRED'
        else:
            row.status='TEST_TRANSFERRED' if cfg['environment']=='test' else 'TRANSFERRED'
            row.paid_at=now()
        details.pop('error',None)
    except HTTPException as exc:
        row.status='FAILED' if exc.status_code==400 else 'UNKNOWN'
        details['error']=str(exc.detail)
    db.get(SystemConfig,'payout:receipt:'+row.reference).value=json.dumps(details)
    db.add(AuditEvent(action='payout-status-updated',target=row.reference,details=row.status))
    db.commit()
    return receipt(db,row)
