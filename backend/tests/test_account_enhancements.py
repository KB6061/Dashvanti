import io
import secrets
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select, update
from backend.db import Session, Base, engine
from backend.models import User, Customer, Restaurant, MenuItem, Order, Review, SupportTicket
from backend.customer_account_models import CustomerWallet, CustomerWalletTransaction
from backend.account_enhancement_models import EnterpriseAudit, AdminPermission, IncidentAttachment, WalletFunding, GatewayControl, ReviewPublication
from backend.account_enhancement_schemas import TicketInput, TicketAction, FavoriteInput, WalletTransfer, ReviewInput, ReviewAction, WalletInput, GatewayInput
from backend.services import incident_service as incidents, enterprise_audit_service as audits, account_experience_service as experience, wallet_funding_service as wallet, account_gateway_service as gateways


class AccountEnhancementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        audits.install()

    def setUp(self):
        self.db=Session()
        from backend.services.auth_service import passwords
        code=secrets.token_hex(6)
        self.user=User(name='Customer',email=code+'@example.com',password=passwords.hash('test-password-123'),role='customer',country='US')
        self.other=User(name='Other',email=code+'-other@example.com',password='x',role='customer',country='US')
        self.admin=User(name='Private Employee Name',email=code+'-admin@example.com',password='x',role='admin')
        self.owner=User(name='Store',email=code+'-store@example.com',password='x',role='restaurant')
        self.db.add_all([self.user,self.other,self.admin,self.owner]);self.db.flush()
        self.db.add_all([Customer(id=self.user.id),Customer(id=self.other.id),Restaurant(id=self.owner.id,name='Store',address='Address',country='US')]);self.db.flush()

    def tearDown(self):
        self.db.rollback();self.db.close()

    def ticket(self,user=None):
        return incidents.create(self.db,user or self.user,TicketInput(category='Late Delivery',description='Please help'))

    def order(self):
        row=Order(customer_id=self.user.id,restaurant_id=self.owner.id,request_key=secrets.token_hex(8),status='DELIVERED',mode='delivery',address='Home',total=Decimal('10'))
        self.db.add(row);self.db.flush();return row

    def test_global_incident_numbers_and_ownership(self):
        first=self.ticket();second=self.ticket(self.other)
        self.assertRegex(first['number'],r'^INC\d{10}$');self.assertGreater(second['id'],first['id'])
        with self.assertRaises(HTTPException):incidents.owned(self.db,self.other,first['id'])
        self.assertEqual(incidents.listing(self.db,self.user,q=second['number'])['total'],0)

    def test_support_internal_notes_and_employee_names_are_private(self):
        ticket=self.ticket()
        incidents.change(self.db,self.admin,ticket['id'],TicketAction(action='assign',assignee_id=self.admin.id))
        incidents.change(self.db,self.admin,ticket['id'],TicketAction(action='note',body='Secret investigation'))
        incidents.change(self.db,self.admin,ticket['id'],TicketAction(action='reply',body='We are helping'))
        data=incidents.public_ticket(self.db,incidents.owned(self.db,self.user,ticket['id']),self.user,True)
        self.assertNotIn('Secret investigation',str(data));self.assertNotIn(self.admin.name,str(data))
        self.assertEqual(data['assigned_to'],'Support Team');self.assertEqual(data['messages'][0]['user'],'Support Team')

    def test_customers_cannot_assign_close_or_escalate(self):
        ticket=self.ticket()
        for action in ['assign','status','escalate','note']:
            with self.assertRaises(HTTPException):incidents.change(self.db,self.user,ticket['id'],TicketAction(action=action,body='No',status='Closed'))

    def test_merge_prevents_cross_account_exposure(self):
        first=self.ticket();second=self.ticket(self.other)
        with self.assertRaises(HTTPException):incidents.change(self.db,self.admin,first['id'],TicketAction(action='merge',merge_into=second['id']))

    def test_favorite_menu_ownership_and_idempotency(self):
        item=MenuItem(restaurant_id=self.owner.id,name='Biryani',price=Decimal('12'));self.db.add(item);self.db.flush()
        data=FavoriteInput(kind='menu',target_id=item.id,enabled=True)
        experience.favorite(self.db,self.user,data);experience.favorite(self.db,self.user,data)
        self.assertEqual(len(experience.favorites(self.db,self.user)['menu_items']),1)
        self.assertEqual(experience.favorites(self.db,self.other)['menu_items'],[])

    def test_review_approval_and_helpful_vote_idempotency(self):
        order=self.order();result=experience.review_save(self.db,self.user,ReviewInput(order_id=order.id,rating=5,title='Great',comment='Fresh food'))
        self.assertEqual(experience.reviews(self.db,self.owner.id)['total'],0)
        experience.review_action(self.db,self.admin,result['id'],ReviewAction(action='approve'))
        self.assertEqual(experience.reviews(self.db,self.owner.id)['total'],1)
        experience.review_action(self.db,self.other,result['id'],ReviewAction(action='helpful'))
        self.assertEqual(experience.reviews(self.db,self.owner.id)['items'][0]['helpful'],1)
        experience.review_save(self.db,self.user,ReviewInput(order_id=order.id,rating=3,comment='Changed'))
        self.assertEqual(experience.reviews(self.db,self.owner.id)['total'],0)

    def test_review_requires_owned_completed_order(self):
        order=self.order()
        with self.assertRaises(HTTPException):experience.review_save(self.db,self.other,ReviewInput(order_id=order.id,rating=5,comment='No'))

    def test_wallet_transfer_is_balanced_and_idempotent(self):
        self.db.add(CustomerWallet(customer_id=self.user.id,currency='USD',balance=Decimal('10')));self.db.flush()
        data=WalletTransfer(recipient_email=self.other.email,amount=Decimal('3'),request_key=secrets.token_hex(16),current_password='test-password-123')
        wallet.transfer(self.db,self.user,data);wallet.transfer(self.db,self.user,data)
        self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('7'))
        self.assertEqual(self.db.get(CustomerWallet,(self.other.id,'USD')).balance,Decimal('3'))
        self.assertEqual(sum(self.db.scalars(select(CustomerWalletTransaction.amount))),Decimal('0'))

    def test_pending_or_sandbox_payment_never_credits_real_wallet(self):
        row=WalletFunding(id=secrets.token_hex(16),customer_id=self.user.id,request_key=secrets.token_hex(16),provider='stripe',provider_reference='cs_'+secrets.token_hex(10),amount=Decimal('5'),currency='USD')
        self.db.add(row);self.db.flush()
        with patch.object(wallet,'verified_payment',return_value=(False,True)):wallet.complete(self.db,self.user,row.id)
        self.assertIsNone(self.db.get(CustomerWallet,(self.user.id,'USD')))
        with patch.object(wallet,'verified_payment',return_value=(True,False)):wallet.complete(self.db,self.user,row.id)
        self.assertEqual(row.status,'test_complete');self.assertIsNone(self.db.get(CustomerWallet,(self.user.id,'USD')))

    def test_verified_funding_credits_exactly_once_and_checks_owner(self):
        row=WalletFunding(id=secrets.token_hex(16),customer_id=self.user.id,request_key=secrets.token_hex(16),provider='stripe',provider_reference='cs_'+secrets.token_hex(10),amount=Decimal('5'),currency='USD')
        self.db.add(row);self.db.flush()
        with self.assertRaises(HTTPException):wallet.complete(self.db,self.other,row.id)
        with patch.object(wallet,'verified_payment',return_value=(True,True)):
            wallet.complete(self.db,self.user,row.id);wallet.complete(self.db,self.user,row.id)
        self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('5'))

    def test_admin_orm_and_bulk_changes_are_audited_without_secrets(self):
        self.db.info['audit_actor']={'id':self.admin.id,'name':self.admin.name,'role':'admin'}
        self.owner.password='very-secret-value';self.db.flush()
        self.db.execute(update(Restaurant).where(Restaurant.id==self.owner.id).values(name='Updated'))
        self.db.flush()
        records=list(self.db.scalars(select(EnterpriseAudit)))
        self.assertNotIn('very-secret-value',str([(row.old_value,row.new_value) for row in records]))
        self.assertTrue(any(row.module=='restaurants' and row.action=='update' for row in records))

    def test_rollback_requires_permission_and_rejects_stale_version(self):
        self.db.info['audit_actor']={'id':self.admin.id,'name':self.admin.name,'role':'admin'}
        store=self.db.get(Restaurant,self.owner.id);store.name='Second';self.db.flush()
        audit=self.db.scalar(select(EnterpriseAudit).where(EnterpriseAudit.module=='restaurants').order_by(EnterpriseAudit.id.desc()))
        with self.assertRaises(HTTPException):audits.rollback(self.db,self.admin,audit.id,'Undo update')
        self.db.add(AdminPermission(user_id=self.admin.id,audit_rollback=True));self.db.flush()
        store.name='Third';self.db.flush()
        with self.assertRaises(HTTPException):audits.rollback(self.db,self.admin,audit.id,'Undo update')

    def test_rollback_restores_previous_values(self):
        self.db.info['audit_actor']={'id':self.admin.id,'name':self.admin.name,'role':'admin'}
        self.db.add(AdminPermission(user_id=self.admin.id,audit_rollback=True));self.db.flush()
        store=self.db.get(Restaurant,self.owner.id);store.name='Second';self.db.flush()
        audit=self.db.scalar(select(EnterpriseAudit).where(EnterpriseAudit.module=='restaurants').order_by(EnterpriseAudit.id.desc()))
        audits.rollback(self.db,self.admin,audit.id,'Restore name')
        self.assertEqual(store.name,'Store')

    def test_audit_is_append_only(self):
        audits.record(self.db,{'id':self.admin.id,'name':self.admin.name},'update','example',{}, {},{})
        self.db.flush();row=self.db.scalar(select(EnterpriseAudit));row.reason='Tampered'
        with self.assertRaises(HTTPException):self.db.flush()

    def test_india_gateways_are_hidden_for_us_and_unconfigured_providers(self):
        self.db.add(GatewayControl(name='phonepe',enabled=True,countries='IN'));self.db.flush()
        with patch.object(gateways,'configured',return_value=True):self.assertNotIn('phonepe',[row['name'] for row in gateways.methods(self.db,self.user)])
        self.user.country='IN'
        with patch.object(gateways,'configured',return_value=False):self.assertEqual(gateways.methods(self.db,self.user),[])

    def test_csv_export_neutralizes_formulas(self):
        value=incidents.csv_export([{'number':'INC0000000001','customer_name':'=IMPORTDATA("secret")'}])
        self.assertIn("'=IMPORTDATA",value)

    def test_sensitive_system_config_values_are_redacted(self):
        self.assertEqual(audits.safe({'key':'stripe_secret_key','value':'secret'})['value'],'[redacted]')

    def test_api_requires_authentication_and_admin_role(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.db import get_db
        from backend.routers.account_experience import router
        app=FastAPI();app.include_router(router,prefix='/api')
        app.dependency_overrides[get_db]=lambda:self.db
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/account-experience/tickets').status_code,401)
            self.assertEqual(client.get('/api/account-experience/admin/audit',headers=self.authorization(self.user)).status_code,403)
            self.assertEqual(client.get('/api/account-experience/admin/audit',headers=self.authorization(self.admin)).status_code,200)

    def authorization(self,user):
        import jwt,time
        from backend.config import settings
        token=jwt.encode({'sub':str(user.id),'ver':user.token_version,'iat':int(time.time()),'exp':int(time.time())+60,'iss':'dashvanti-api','aud':'dashvanti'},settings.jwt_secret,algorithm='HS256')
        return {'Authorization':'Bearer '+token}

    def test_api_ticket_flow_enforces_ownership_and_hides_internal_notes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.db import get_db
        from backend.routers.account_experience import router
        app=FastAPI();app.include_router(router,prefix='/api');app.dependency_overrides[get_db]=lambda:self.db
        with TestClient(app) as client:
            result=client.post('/api/account-experience/tickets',json={'category':'Missing Item','description':'Missing bread'},headers=self.authorization(self.user))
            self.assertEqual(result.status_code,201);ticket_id=result.json()['id']
            self.assertEqual(client.get(f'/api/account-experience/tickets/{ticket_id}',headers=self.authorization(self.other)).status_code,404)
            self.assertEqual(client.post(f'/api/account-experience/tickets/{ticket_id}',json={'action':'note','body':'Internal evidence'},headers=self.authorization(self.admin)).status_code,200)
            visible=client.get(f'/api/account-experience/tickets/{ticket_id}',headers=self.authorization(self.user)).json()
            self.assertNotIn('Internal evidence',str(visible));self.assertNotIn(self.admin.name,str(visible))

    def test_wallet_transfer_rejects_currency_mismatch_and_insufficient_balance(self):
        self.other.country='IN'
        data=WalletTransfer(recipient_email=self.other.email,amount=Decimal('3'),request_key=secrets.token_hex(16),current_password='test-password-123')
        with self.assertRaises(HTTPException):wallet.transfer(self.db,self.user,data)
        self.other.country='US'
        with self.assertRaises(HTTPException):wallet.transfer(self.db,self.user,data)

    def test_gateway_controls_reject_us_phonepe_and_customer_changes(self):
        data=GatewayInput(name='phonepe',enabled=True,countries=['US'],reason='Test scope')
        with self.assertRaises(HTTPException):gateways.update(self.db,self.admin,data)
        with self.assertRaises(HTTPException):gateways.update(self.db,self.user,data)

    def test_complete_account_snapshot_uses_extended_database_records(self):
        from backend.services.customer_account_service import snapshot
        result=snapshot(self.db,self.user)
        self.assertEqual(result['currency'],'USD');self.assertIn('favorites_detail',result)
        self.assertIn('gateways',result);self.assertIn('avatar',result)
        self.assertFalse(result['card_setup_available'])

    def test_india_and_usa_state_lists_are_complete(self):
        from backend.services.account_location_service import STATES
        self.assertEqual(len(STATES['US']),51);self.assertEqual(len(STATES['IN']),36)
        self.assertIn('Tennessee',STATES['US']);self.assertIn('Maharashtra',STATES['IN'])

    def test_wallet_webhooks_require_signature_and_credit_only_once(self):
        import json,hashlib,hmac,time
        from backend.services import wallet_webhook_service as webhooks
        row=WalletFunding(id=secrets.token_hex(16),customer_id=self.user.id,request_key=secrets.token_hex(16),provider='stripe',provider_reference='cs_'+secrets.token_hex(10),amount=Decimal('5'),currency='USD',environment='production')
        self.db.add(row);self.db.flush()
        raw=json.dumps({'data':{'object':{'client_reference_id':row.id}}}).encode();timestamp=str(int(time.time()));secret='local-webhook-test'
        signature=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        with patch.dict('os.environ',{'STRIPE_WALLET_WEBHOOK_SECRET':secret}):
            with self.assertRaises(HTTPException):webhooks.receive(self.db,'stripe',raw,{'stripe-signature':'t='+timestamp+',v1=bad'})
            with patch.object(wallet,'verified_payment',return_value=(True,True)):
                for _ in range(2):webhooks.receive(self.db,'stripe',raw,{'stripe-signature':'t='+timestamp+',v1='+signature})
        self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('5'))

    def test_payment_verification_rejects_wrong_amount_currency_and_environment(self):
        row=WalletFunding(id=secrets.token_hex(16),customer_id=self.user.id,request_key=secrets.token_hex(16),provider='stripe',provider_reference='cs_test',amount=Decimal('5'),currency='USD',environment='production')
        for amount,currency,live in [(999,'usd',True),(500,'inr',True),(500,'usd',False)]:
            with patch.object(wallet,'stripe_request',return_value={'client_reference_id':row.id,'amount_total':amount,'currency':currency,'livemode':live,'payment_status':'paid'}):
                with self.assertRaises(HTTPException):wallet.verified_payment(self.db,row)

    def test_ticket_attachments_do_not_allow_cross_account_upload(self):
        ticket=self.ticket()
        file=SimpleNamespace(file=io.BytesIO(b'not an image'),filename='fake.jpg',content_type='image/jpeg')
        with self.assertRaises(HTTPException):incidents.upload(self.db,self.other,ticket['id'],file)
        with self.assertRaises(HTTPException):incidents.upload(self.db,self.user,ticket['id'],file)

    def test_google_location_initialization_never_guesses_country(self):
        from backend.services.account_location_service import ip_profile
        request=SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),headers={})
        self.assertIsNone(ip_profile(request))

    def funding(self,provider='square',currency='USD'):
        row=WalletFunding(id=secrets.token_hex(16),customer_id=self.user.id,request_key=secrets.token_hex(16),provider=provider,provider_reference='ref_'+secrets.token_hex(8),amount=Decimal('5'),currency=currency,environment='production')
        self.db.add(row);self.db.flush();return row

    def test_square_requires_completed_payment_with_exact_reference_and_amount(self):
        from backend.services import wallet_provider_service as providers
        row=self.funding()
        total={'amount':500,'currency':'USD'}
        order={'reference_id':row.id,'total_money':total,'tenders':[{'payment_id':'payment_1'}]}
        payment={'order_id':row.provider_reference,'amount_money':total,'status':'COMPLETED'}
        with patch.dict('os.environ',{'SQUARE_ACCESS_TOKEN':'test','SQUARE_ENVIRONMENT':'production'}),patch.object(providers,'request',side_effect=[{'order':order},{'payment':payment}]):
            self.assertEqual(providers.verify(self.db,row),(True,True))
        payment['amount_money']={'amount':900,'currency':'USD'}
        with patch.dict('os.environ',{'SQUARE_ACCESS_TOKEN':'test','SQUARE_ENVIRONMENT':'production'}),patch.object(providers,'request',side_effect=[{'order':order},{'payment':payment}]):
            with self.assertRaises(HTTPException):providers.verify(self.db,row)

    def test_authorize_requires_matching_customer_and_invoice(self):
        from backend.services import wallet_provider_service as providers
        from backend.account_enhancement_models import WalletCheckout
        row=self.funding('authorize_net')
        self.db.add(WalletCheckout(funding_id=row.id,payment_reference='1234'));self.db.flush()
        transaction={'order':{'invoiceNumber':row.provider_reference},'customer':{'id':str(self.user.id)},'authAmount':'5.00','transactionStatus':'capturedPendingSettlement'}
        with patch.object(providers,'authorize',return_value={'transaction':transaction}):self.assertEqual(providers.verify(self.db,row),(True,True))
        transaction['customer']['id']=str(self.other.id)
        with patch.object(providers,'authorize',return_value={'transaction':transaction}):
            with self.assertRaises(HTTPException):providers.verify(self.db,row)

    def test_paytm_callback_checks_signature_and_server_status(self):
        from urllib.parse import urlencode
        from paytmchecksum import PaytmChecksum
        from backend.services import wallet_webhook_service as hooks
        row=self.funding('paytm','INR')
        values={'ORDERID':row.provider_reference,'MID':'testMID','STATUS':'TXN_SUCCESS'}
        secret='1234567890123456';values['CHECKSUMHASH']=PaytmChecksum.generateSignature(values,secret)
        with patch.dict('os.environ',{'PAYTM_MERCHANT_KEY':secret}),patch.object(wallet,'verified_payment',return_value=(False,True)):
            self.assertEqual(hooks.receive(self.db,'paytm',urlencode(values).encode(),{})['status'],'pending')
            values['STATUS']='TAMPERED'
            with self.assertRaises(HTTPException):hooks.receive(self.db,'paytm',urlencode(values).encode(),{})

    def test_square_callback_signature_binds_exact_callback_url(self):
        import json,hmac,hashlib,base64
        from backend.services import wallet_webhook_service as hooks
        row=self.funding();raw=json.dumps({'data':{'object':{'payment':{'order_id':row.provider_reference}}}}).encode()
        url='https://customer.dashvanti.com/customer/wallet-webhook/square';secret='square-test'
        signature=base64.b64encode(hmac.new(secret.encode(),url.encode()+raw,hashlib.sha256).digest()).decode()
        with patch.dict('os.environ',{'SQUARE_WALLET_WEBHOOK_URL':url,'SQUARE_WALLET_WEBHOOK_SECRET':secret}),patch.object(wallet,'verified_payment',return_value=(True,True)):
            hooks.receive(self.db,'square',raw,{'x-square-hmacsha256-signature':signature})
            self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('5'))
            with self.assertRaises(HTTPException):hooks.receive(self.db,'square',raw,{'x-square-hmacsha256-signature':'bad'})

    def test_stripe_intent_rejects_wrong_wallet_instrument(self):
        row=self.funding('apple_pay');row.provider_reference='pi_local'
        result={'metadata':{'wallet_funding_id':row.id},'amount':500,'currency':'usd','livemode':True,'status':'succeeded','amount_received':500,'latest_charge':{'payment_method_details':{'card':{'wallet':{'type':'google_pay'}}}}}
        with patch.object(wallet,'stripe_request',return_value=result):
            with self.assertRaises(HTTPException):wallet.verified_payment(self.db,row)

    def test_checkout_tokens_are_scoped_to_payment_owner_and_redacted_from_audit(self):
        from backend.account_enhancement_models import WalletCheckout
        from backend.services.wallet_provider_service import checkout
        row=self.funding('authorize_net');self.db.add(WalletCheckout(funding_id=row.id,payload='{"token":"private-token"}'));self.db.flush()
        self.assertEqual(checkout(self.db,self.user,row.id)['token'],'private-token')
        with self.assertRaises(HTTPException):checkout(self.db,self.other,row.id)
        self.assertEqual(audits.safe({'payload':'{"token":"private-token"}'})['payload'],'[redacted]')

    def test_wallet_refund_requires_paid_production_payment_and_is_idempotent(self):
        import json
        from backend.models import SystemConfig
        from backend.payment_models import Payment,PaymentOrder,AdminSettings
        from backend.account_enhancement_schemas import WalletRefundInput
        from backend.services.wallet_refund_service import credit
        order=self.order()
        settings=AdminSettings(environment='production',api_version='v2',encrypted_credentials='test')
        self.db.add(settings);self.db.flush()
        payment=Payment(merchant_order_id='DVP_'+secrets.token_hex(8),settings_id=settings.id,request_key=secrets.token_hex(8),amount=1000,currency='USD',country='US',environment='production',status='COMPLETED')
        self.db.add(payment);self.db.flush();self.db.add(PaymentOrder(payment_id=payment.id,order_id=order.id,original_order_id=order.id))
        key='refund:'+secrets.token_hex(8)
        self.db.add(SystemConfig(key=key,value=json.dumps({'order_id':order.id,'amount':'5.00','status':'PENDING'})));self.db.flush()
        data=WalletRefundInput(refund_id=key,reason='Verified missing item')
        for _ in range(2):credit(self.db,self.admin,data)
        self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('5'))

    def test_nested_admin_sessions_inherit_audit_identity(self):
        from backend.audit_context import actor
        from backend.models import SystemConfig
        token=actor.set({'id':self.admin.id,'name':self.admin.name,'role':'admin'})
        try:
            from sqlalchemy.orm import Session as ORMSession
            with ORMSession(bind=self.db.connection(),join_transaction_mode='create_savepoint') as nested:
                nested.add(SystemConfig(key='test-context:'+secrets.token_hex(8),value='test'))
                nested.flush()
                self.assertEqual(nested.info['audit_actor']['id'],self.admin.id)
                self.assertTrue(nested.scalar(select(EnterpriseAudit).where(EnterpriseAudit.actor_id==self.admin.id)))
                nested.rollback()
        finally:actor.reset(token)
