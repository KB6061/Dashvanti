import io
import secrets
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from fastapi import HTTPException
from sqlalchemy import select
from backend.db import Session
from backend.models import Driver, User, Order, Restaurant, Customer, now
from backend.models_driver_partner import DriverDocument, DriverDeliveryOTP, DriverWallet, DriverWithdrawal, DriverPartner, DriverDeposit
from backend.schemas_driver_partner import Registration, AdminAction, WithdrawalInput, WithdrawalAction
from backend.services import driver_partner_service as service


class DriverPartnerTests(unittest.TestCase):
    def setUp(self):
        self.db = Session()
        self.user = User(name='Partner audit', email='partner-audit-'+secrets.token_hex(8)+'@example.com', password='not-a-login', role='driver', phone='')
        self.db.add(self.user); self.db.flush()
        self.db.add(Driver(id=self.user.id, online=False)); self.db.flush()

    def tearDown(self):
        self.db.rollback(); self.db.close()

    def data(self):
        return Registration(first_name='Test', last_name='Driver', mobile='+919'+str(secrets.randbelow(10**9)).zfill(9), email=self.user.email,
            date_of_birth=date(1990,1,1), gender='Other', address='Test Street, Pune, India', aadhaar='2'+str(secrets.randbelow(10**11)).zfill(11),
            pan='ABCDE1234F', license_number='MH12345678', vehicle_type='Bike', vehicle_number='MH12TEST', account_holder='Test Driver', account_number='123456789012', ifsc='HDFC0001234', upi='test@upi', emergency_name='Contact', emergency_relationship='Sibling', emergency_phone='+919999999999', nominee_name='Nominee', nominee_relationship='Sibling', nominee_phone='+919999999999', terms=True, driver_policy=True, insurance_policy=True, identity_consent=True)

    def order(self, status='DELIVERED'):
        customer=User(name='Partner audit',email='partner-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='customer')
        restaurant=User(name='Partner audit',email='partner-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='restaurant')
        self.db.add_all([customer,restaurant]);self.db.flush()
        self.db.add_all([Customer(id=customer.id),Restaurant(id=restaurant.id,name='Audit restaurant',currency='INR')]);self.db.flush()
        row=Order(customer_id=customer.id,restaurant_id=restaurant.id,driver_id=self.user.id,request_key=secrets.token_hex(16),status=status,mode='delivery',currency='INR',address='Test address',total=Decimal(100),delivery_fee=Decimal(100),tip=Decimal(0))
        self.db.add(row);self.db.flush();return row

    def test_sensitive_profile_masked_and_encrypted(self):
        data=self.data(); result=service.save_registration(self.db,self.user,data)
        row=self.db.get(DriverPartner,self.user.id)
        self.assertNotIn(data.account_number,row.profile)
        self.assertNotIn(data.aadhaar,row.profile)
        self.assertEqual(result['profile']['account_number'],'********9012')
        self.assertEqual(result['profile']['aadhaar'],'********'+data.aadhaar[-4:])

    def test_duplicate_identity_blocked(self):
        data=self.data(); service.save_registration(self.db,self.user,data)
        other=User(name='Other', email='partner-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='driver')
        self.db.add(other);self.db.flush();self.db.add(Driver(id=other.id));self.db.flush()
        with self.assertRaises(HTTPException) as exc:
            service.save_registration(self.db,other,data.model_copy(update={'email':other.email,'mobile':'+918'+str(secrets.randbelow(10**9)).zfill(9)}))
        self.assertEqual(exc.exception.status_code,409)

    def test_missing_documents_prevent_submission(self):
        service.save_registration(self.db,self.user,self.data())
        with self.assertRaises(HTTPException): service.submit(self.db,self.user)
        self.assertEqual(self.db.get(DriverPartner,self.user.id).status,'DRAFT')

    def test_unreviewed_documents_prevent_approval(self):
        service.save_registration(self.db,self.user,self.data())
        for kind in service.DOCUMENTS:
            self.db.add(DriverDocument(driver_id=self.user.id,kind=kind,encrypted_path='/not-real',mime='image/jpeg',expires_on=date.today()+timedelta(days=365) if kind in service.EXPIRING else None))
        self.db.flush();service.submit(self.db,self.user)
        with self.assertRaises(HTTPException): service.admin_action(self.db,self.user.id,AdminAction(action='APPROVE',notes='Review done'))

    def test_deposit_required_and_deactivation_permanent(self):
        row=service.partner(self.db,self.user.id);row.status='APPROVED';row.account_status='ACTIVE'
        with patch.object(service,'verification',return_value={'issues':[]}):
            with self.assertRaises(HTTPException): service.ensure_active(self.db,self.user.id)
        with patch('backend.services.redis_geo_service.remove'):
            service.admin_action(self.db,self.user.id,AdminAction(action='DEACTIVATE',notes='Confirmed policy violation'))
        with self.assertRaises(HTTPException): service.admin_action(self.db,self.user.id,AdminAction(action='REACTIVATE',notes='Try to restore'))

    def test_manager_cannot_deactivate(self):
        service.partner(self.db,self.user.id)
        with self.assertRaises(HTTPException) as exc:
            service.admin_action(self.db,self.user.id,AdminAction(action='DEACTIVATE',notes='test'),SimpleNamespace(id=self.user.id,role='operations_manager'))
        self.assertEqual(exc.exception.status_code,403)

    def test_private_document_other_driver_denied(self):
        row=DriverDocument(driver_id=self.user.id,kind='selfie',encrypted_path='/not-real',mime='image/jpeg');self.db.add(row);self.db.flush()
        with self.assertRaises(HTTPException) as exc: service.document_bytes(self.db,row.id,SimpleNamespace(id=self.user.id+1,role='driver'))
        self.assertEqual(exc.exception.status_code,404)

    def test_withdrawal_reserves_once_and_rejection_restores_once(self):
        service.save_registration(self.db,self.user,self.data())
        order=self.order();service.earning(self.db,order);self.db.flush()
        data=WithdrawalInput(request_key='request123',amount=Decimal(40),currency='INR',method='BANK')
        first=service.withdraw(self.db,self.user,data);second=service.withdraw(self.db,self.user,data)
        self.assertEqual(first['id'],second['id'])
        wallet=self.db.scalar(select(DriverWallet).where(DriverWallet.driver_id==self.user.id))
        self.assertEqual(wallet.balance,Decimal(60))
        service.withdrawal_action(self.db,first['id'],WithdrawalAction(status='REJECTED',reference='Not transferred'))
        self.assertEqual(wallet.balance,Decimal(100))
        with self.assertRaises(HTTPException):service.withdrawal_action(self.db,first['id'],WithdrawalAction(status='REJECTED',reference='Not transferred'))

    def test_document_rejects_invalid_image_before_disk_write(self):
        service.partner(self.db,self.user.id)
        with self.assertRaises(HTTPException): service.upload(self.db,self.user,'selfie',SimpleNamespace(file=io.BytesIO(b'<script>bad</script>')))

    def test_underage_rejected(self):
        data=self.data().model_copy(update={'date_of_birth':date.today()-timedelta(days=365*16)})
        with self.assertRaises(HTTPException):service.save_registration(self.db,self.user,data)

    def test_paid_admin_payout_cannot_be_withdrawn_again(self):
        from backend.models import PayoutTransaction
        service.save_registration(self.db,self.user,self.data())
        order=self.order();service.earning(self.db,order);self.db.flush()
        self.db.add(PayoutTransaction(order_id=order.id,payee_id=self.user.id,payee_role='driver',amount=Decimal(100),status='PAID',method='MANUAL',reference='audit-'+secrets.token_hex(12)));self.db.flush()
        with self.assertRaises(HTTPException):service.withdraw(self.db,self.user,WithdrawalInput(request_key='withdraw123',amount=Decimal(1),currency='INR',method='BANK'))

    def test_delivery_requires_otp_and_credits_once(self):
        from backend.services.delivery_service import transition
        service.partner(self.db,self.user.id)
        order=self.order('ON_THE_WAY_TO_CUSTOMER')
        service.issue_otp(self.db,order);self.db.flush()
        row=self.db.get(DriverDeliveryOTP,order.id)
        with patch.object(service,'ensure_active'),patch('backend.services.tracking_service.states',return_value=('READY_FOR_PICKUP','ON_THE_WAY_TO_CUSTOMER',[])),patch('backend.services.gps_point_service.milestone'):
            with self.assertRaises(HTTPException):transition(self.db,self.user,order.id,'DELIVERED')
            result=service.verify_otp(self.db,self.user,order.id,service.unseal(row.encrypted_code))
            self.assertEqual(result['status'],'DELIVERED')
            with self.assertRaises(HTTPException):service.verify_otp(self.db,self.user,order.id,service.unseal(row.encrypted_code))
        self.db.flush()
        wallet=self.db.scalar(select(DriverWallet).where(DriverWallet.driver_id==self.user.id))
        self.assertEqual(wallet.balance,Decimal(100))

    def test_wrong_otp_increments_persisted_attempt_limit(self):
        order=self.order('ON_THE_WAY_TO_CUSTOMER');service.issue_otp(self.db,order);self.db.flush()
        row=self.db.get(DriverDeliveryOTP,order.id)
        code=service.unseal(row.encrypted_code);wrong='0000' if code!='0000' else '0001'
        with patch.object(self.db,'commit',side_effect=self.db.flush):
            for _ in range(5):
                with self.assertRaises(HTTPException):service.verify_otp(self.db,self.user,order.id,wrong)
        self.assertEqual(row.attempts,5)
        with self.assertRaises(HTTPException):service.verify_otp(self.db,self.user,order.id,code)

    def test_upload_encrypted_and_owner_can_read(self):
        import tempfile
        from pathlib import Path
        from backend.config import settings
        service.partner(self.db,self.user.id)
        image=io.BytesIO();Image.new('RGB',(40,40),(25,100,50)).save(image,'PNG');image.seek(0)
        with tempfile.TemporaryDirectory() as directory,patch.object(settings,'file_root',directory):
            result=service.upload(self.db,self.user,'selfie',SimpleNamespace(file=image))
            row=self.db.get(DriverDocument,result['id'])
            self.assertFalse(Path(row.encrypted_path).read_bytes().startswith(b'\xff\xd8'))
            self.assertTrue(service.document_bytes(self.db,row.id,self.user).startswith(b'\xff\xd8'))

    def test_expired_offer_reassigned_to_next_driver(self):
        from backend.models_driver_partner import DriverOffer
        from backend.services.driver_offer_service import ensure_offer
        order=self.order('ACCEPTED');order.driver_id=None
        other=User(name='Partner audit',email='partner-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='driver')
        self.db.add(other);self.db.flush();self.db.add(Driver(id=other.id,online=True))
        previous=DriverOffer(driver_id=self.user.id,order_id=order.id,expires_at=now()-timedelta(seconds=1));self.db.add(previous);self.db.flush()
        with patch('backend.services.dispatch_service.nearby',return_value=[{'id':other.id}]):
            current=ensure_offer(self.db,order)
        self.assertEqual(previous.status,'EXPIRED');self.assertEqual(current.driver_id,other.id)
        self.assertLessEqual((current.expires_at-now()).total_seconds(),30)

    def test_sandbox_deposit_does_not_activate_driver(self):
        from backend.payment_models import Payment, AdminSettings
        from backend.services.phonepe_service import apply_status
        cfg=AdminSettings(environment='sandbox',api_version='v2',encrypted_credentials=service.seal({}))
        self.db.add(cfg);self.db.flush()
        payment=Payment(user_id=self.user.id,settings_id=cfg.id,merchant_order_id='audit-'+secrets.token_hex(12),request_key=secrets.token_hex(12),amount=100000,currency='INR',country='IN',environment='sandbox',api_version='v2',status='PENDING')
        self.db.add(payment);self.db.flush();deposit=DriverDeposit(driver_id=self.user.id,payment_id=payment.id,amount=Decimal(1000));self.db.add(deposit);self.db.flush()
        row=service.partner(self.db,self.user.id);row.status='APPROVED';row.account_status='ACTIVE'
        apply_status(self.db,payment.id,{'state':'COMPLETED','orderId':'audit-provider-order','amount':100000})
        self.assertEqual(deposit.status,'SANDBOX_PAID')
        with patch.object(service,'verification',return_value={'issues':[]}):
            with self.assertRaises(HTTPException):service.ensure_active(self.db,self.user.id)

    def test_http_role_permissions(self):
        import jwt,time
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.routers.driver_partner import router
        from backend.db import get_db
        from backend.config import settings
        app=FastAPI();app.include_router(router)
        def session():yield self.db
        app.dependency_overrides[get_db]=session
        token=jwt.encode({'sub':str(self.user.id),'ver':self.user.token_version,'iat':int(time.time()),'exp':int(time.time())+300,'iss':'dashvanti-api','aud':'dashvanti'},settings.jwt_secret,algorithm='HS256')
        with TestClient(app) as client:
            auth={'Authorization':'Bearer '+token}
            self.assertIn(client.get('/admin/driver-partners').status_code,{401,403})
            self.assertEqual(client.get('/admin/driver-partners',headers=auth).status_code,403)
            self.assertEqual(client.get('/driver/partner',headers=auth).status_code,200)
            self.user.role='operations_manager';self.db.flush()
            self.assertEqual(client.get('/admin/driver-partners',headers=auth).status_code,200)
            self.assertEqual(client.get(f'/admin/driver-partners/{self.user.id}/bank',headers=auth).status_code,403)
            self.assertEqual(client.post(f'/admin/driver-partners/{self.user.id}/action',headers=auth,json={'action':'DEACTIVATE','notes':'Test denial'}).status_code,403)

    def test_viewing_module_does_not_enroll_existing_driver(self):
        result=service.overview(self.db,self.user.id)
        self.assertFalse(result['enrolled'])
        self.assertIsNone(self.db.get(DriverPartner,self.user.id))
        service.ensure_active(self.db,self.user.id)


if __name__=='__main__': unittest.main()
