import secrets, unittest, time,base64,hashlib,hmac,struct
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select
from backend.db import Session
from backend.models import User,Customer,Restaurant,Order,Address,SupportTicket,Review,Rating
from backend.customer_account_models import CustomerFavorite,CustomerNotificationSettings,CustomerProfile,CustomerReward,CustomerWallet,CustomerWalletTransaction,CustomerSecurity,CustomerLoginHistory
from backend.customer_account_schemas import AccountProfileInput,AccountTwoFactorInput
from backend.services import customer_account_service as service
from backend.services.auth_service import passwords,login

class CustomerAccountTests(unittest.TestCase):
    def setUp(self):
        self.db=Session();key=secrets.token_hex(8)
        self.user=User(name='Account Test',email=key+'@example.com',password=passwords.hash('account-test-password'),role='customer',country='US',phone='')
        self.other=User(name='Other Test',email=key+'-other@example.com',password='x',role='customer',country='IN')
        self.owner=User(name='Store Test',email=key+'-store@example.com',password='x',role='restaurant')
        self.db.add_all([self.user,self.other,self.owner]);self.db.flush()
        self.db.add_all([Customer(id=self.user.id),Customer(id=self.other.id),Restaurant(id=self.owner.id,name='Test store',address='Test')]);self.db.flush()
    def tearDown(self):self.db.rollback();self.db.close()
    def test_snapshot_uses_owned_records_and_currency(self):
        self.db.add(Address(customer_id=self.other.id,label='Private',details='Other address'));self.db.flush()
        data=service.snapshot(self.db,self.user)
        self.assertEqual(data['currency'],'USD');self.assertEqual(data['stats']['addresses'],0)
        self.assertEqual(service.snapshot(self.db,self.other)['currency'],'INR')
        self.assertNotIn('password',data['user']);self.assertNotIn('totp_secret',data['security'])
    def test_favorites_are_real_and_idempotent(self):
        for _ in range(2):service.action(self.db,self.user,'favorite_add',{'restaurant_id':self.owner.id})
        self.assertEqual(service.snapshot(self.db,self.user)['stats']['favorites'],1)
        self.assertEqual(service.snapshot(self.db,self.other)['stats']['favorites'],0)
        service.action(self.db,self.user,'favorite_remove',{'restaurant_id':self.owner.id});self.db.flush()
        self.assertIsNone(self.db.get(CustomerFavorite,(self.user.id,self.owner.id)))
    def test_address_ownership_and_default(self):
        other=Address(customer_id=self.other.id,label='Private',details='Other');self.db.add(other);self.db.flush()
        with self.assertRaises(HTTPException):service.action(self.db,self.user,'address_delete',{'id':other.id})
        with patch('backend.services.restaurant_location_service.geocode',return_value={}):
            service.action(self.db,self.user,'address_save',{'label':'Home','details':'My address','country':'US','is_default':True,'latitude':36.1,'longitude':-86.7,'apartment':'2','instructions':'Door'})
        self.assertEqual(service.snapshot(self.db,self.user)['addresses'][0]['instructions'],'Door')
    def test_profile_sensitive_fields_require_password(self):
        data=AccountProfileInput(first_name='New',email=self.user.email,phone='1234567890',country='US')
        with self.assertRaises(HTTPException):service.save_profile(self.db,self.user,data)
        data.current_password='account-test-password';service.save_profile(self.db,self.user,data)
        self.assertEqual(self.user.phone,'1234567890')
    def test_preferences_and_support_ownership(self):
        service.action(self.db,self.user,'notifications',{key:False for key in service.NOTIFICATION_FIELDS})
        self.assertFalse(self.db.get(CustomerNotificationSettings,self.user.id).push)
        ticket=SupportTicket(user_id=self.other.id,subject='Private',description='Other');self.db.add(ticket);self.db.flush()
        with self.assertRaises(HTTPException):service.action(self.db,self.user,'support_reply',{'id':ticket.id,'body':'No'})
    def test_wallet_currency_and_idempotency(self):
        service.wallet_credit(self.db,self.user,Decimal('3.00'),'manual_credit','test:'+secrets.token_hex(8),'Audit');self.db.flush()
        self.assertEqual(self.db.get(CustomerWallet,(self.user.id,'USD')).balance,Decimal('3'))
        self.assertIsNone(self.db.get(CustomerWallet,(self.user.id,'INR')))
    def test_logout_all_revokes_token_version(self):
        version=self.user.token_version;service.action(self.db,self.user,'logout_all',{'current_password':'account-test-password'})
        self.assertEqual(self.user.token_version,version+1)
    def test_totp_login_challenge_and_replay_protection(self):
        result=service.action(self.db,self.user,'totp_setup',{'current_password':'account-test-password'})
        step=int(time.time()//30);digest=hmac.new(base64.b32decode(result['secret']),struct.pack('>Q',step),hashlib.sha1).digest();offset=digest[-1]&15;code=str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
        service.action(self.db,self.user,'totp_enable',{'current_password':'account-test-password','code':code})
        challenge=login(self.db,SimpleNamespace(email=self.user.email,password='account-test-password',role='customer'))
        self.assertTrue(challenge['two_factor_required']);self.assertNotIn('access_token',challenge)
        with self.assertRaises(HTTPException):service.verify_totp(self.db,self.user,code)
    def test_payment_setup_ownership_and_no_card_numbers(self):
        with patch.object(service,'stripe_request',return_value={'customer':'other','metadata':{},'status':'complete'}):
            with self.assertRaises(HTTPException):service.action(self.db,self.user,'payment_complete',{'session_id':'cs_test'})
        data=service.export(self.db,self.user);self.assertNotIn('provider_token',str(data));self.assertNotIn('totp_secret',str(data))
    def test_deletion_request_requires_confirmation(self):
        with self.assertRaises(HTTPException):service.action(self.db,self.user,'delete_request',{'current_password':'account-test-password','confirm':'no'})
        service.action(self.db,self.user,'delete_request',{'current_password':'account-test-password','confirm':'DELETE'})
        self.assertIsNotNone(self.db.get(CustomerSecurity,self.user.id).deletion_requested_at)
