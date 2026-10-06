import json
import secrets
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
from backend.db import Session
from backend.models import User, Driver, Customer, Restaurant, Order, PayoutTransaction, now
from backend.models_driver_partner import DriverPartner, DriverDocument, DriverVerification, DriverDeposit, DriverWallet, DriverEarning, DriverWithdrawal, DriverWithdrawalAllocation, DriverIncident, DriverNominee, DriverInsurance, DriverInsuranceClaim, DriverOffer, DriverPartnerNotice, DriverPushDevice
from backend.payment_models import Payment, Refund, AdminSettings
from backend.services import driver_agreement_service as agreements, driver_removal_service as cleanup
from backend.services.operations_service import admin_delete_user
from backend.schemas_driver_agreement import AgreementRead, AgreementAccept


class DriverRemovalTests(unittest.TestCase):
    def setUp(self):
        self.db=Session()
        self.user=User(name='Delete audit',email='delete-audit-'+secrets.token_hex(8)+'@example.com',role='driver',password='x')
        self.db.add(self.user);self.db.flush();self.db.add(Driver(id=self.user.id,online=False));self.db.flush()

    def tearDown(self):
        self.db.rollback();self.db.close()

    def test_all_partner_dependencies_removed_and_history_preserved(self):
        customer=User(name='Audit customer',email='delete-audit-'+secrets.token_hex(8)+'@example.com',role='customer',password='x')
        restaurant=User(name='Audit restaurant',email='delete-audit-'+secrets.token_hex(8)+'@example.com',role='restaurant',password='x')
        other=User(name='Other audit driver',email='delete-audit-'+secrets.token_hex(8)+'@example.com',role='driver',password='x')
        self.db.add_all([customer,restaurant,other]);self.db.flush()
        self.db.add_all([Customer(id=customer.id),Restaurant(id=restaurant.id,name='Delete audit'),Driver(id=other.id,online=False)]);self.db.flush()
        order=Order(customer_id=customer.id,restaurant_id=restaurant.id,driver_id=self.user.id,status='DELIVERED',request_key=secrets.token_hex(16),mode='delivery',currency='INR',total=Decimal(100),delivery_fee=Decimal(10),address='Audit address')
        settings=AdminSettings(environment='sandbox',api_version='v2',encrypted_credentials='')
        self.db.add_all([order,settings]);self.db.flush()
        payment=Payment(user_id=self.user.id,settings_id=settings.id,merchant_order_id='audit-'+secrets.token_hex(16),request_key=secrets.token_hex(16),amount=100000,currency='INR',country='IN',environment='sandbox',api_version='v2',status='COMPLETED')
        payout=PayoutTransaction(order_id=order.id,payee_id=self.user.id,payee_role='driver',amount=Decimal(10),status='PAID',method='MANUAL',reference='audit-'+secrets.token_hex(12))
        withdrawal=DriverWithdrawal(driver_id=self.user.id,request_key=secrets.token_hex(12),amount=Decimal(10),currency='INR',method='BANK')
        incident=DriverIncident(driver_id=self.user.id,order_id=order.id,kind='Other',description='Audit incident')
        self.db.add_all([payment,payout,withdrawal,incident]);self.db.flush()
        refund=Refund(payment_id=payment.id,merchant_refund_id='audit-'+secrets.token_hex(12),request_key=secrets.token_hex(12),amount=100000,reason='Audit refund',status='COMPLETED')
        self.db.add(refund);self.db.flush()
        self.db.add_all([
            DriverPartner(driver_id=self.user.id),DriverDocument(driver_id=self.user.id,kind='selfie',encrypted_path='/not-real.jpg',mime='image/jpeg'),
            DriverVerification(driver_id=self.user.id,report='{}'),DriverVerification(driver_id=other.id,reviewer_id=self.user.id,report='{}'),
            DriverDeposit(driver_id=self.user.id,payment_id=payment.id,refund_id=refund.id,amount=Decimal(1000)),DriverWallet(driver_id=self.user.id,currency='INR'),
            DriverEarning(driver_id=self.user.id,order_id=order.id,currency='INR',base_pay=Decimal(10)),DriverWithdrawalAllocation(withdrawal_id=withdrawal.id,payout_id=payout.id),
            DriverNominee(driver_id=self.user.id,encrypted_details='encrypted'),DriverInsurance(driver_id=self.user.id),
            DriverInsuranceClaim(driver_id=self.user.id,incident_id=incident.id,reference='audit-'+secrets.token_hex(12),amount=Decimal(10)),
            DriverOffer(driver_id=self.user.id,order_id=order.id,expires_at=now()+timedelta(seconds=30)),
            DriverPartnerNotice(driver_id=self.user.id,event='AUDIT',body='audit',recipient=self.user.email,channel='EMAIL',status='SKIPPED'),
            DriverPushDevice(driver_id=self.user.id,installation_id=secrets.token_hex(12),token=secrets.token_hex(24),token_version=self.user.token_version)])
        value=agreements.start(self.db,self.user)
        agreements.record_read(self.db,value['token'],AgreementRead(agreement_version=value['agreement_version'],scroll_completed=True),self.user)
        agreements.accept(self.db,value['token'],AgreementAccept(agreement_version=value['agreement_version'],full_legal_name=self.user.name,acknowledgements={item['key']:True for item in value['acknowledgements']}),{},self.user)
        self.db.flush();driver_id=self.user.id;order_id=order.id;payment_id=payment.id;refund_id=refund.id
        admin_delete_user(self.db,driver_id);self.db.expire_all()
        self.assertIsNone(self.db.get(User,driver_id));self.assertIsNone(self.db.get(Driver,driver_id))
        self.assertIsNone(self.db.get(Order,order_id).driver_id)
        self.assertIsNone(self.db.get(Payment,payment_id).user_id);self.assertIsNotNone(self.db.get(Refund,refund_id))
        self.assertIsNotNone(self.db.get(Driver,other.id))
        self.assertIsNone(self.db.scalar(select(DriverVerification).where(DriverVerification.driver_id==other.id)).reviewer_id)
        for model in [DriverPartner,DriverDocument,DriverVerification,DriverDeposit,DriverWallet,DriverEarning,DriverWithdrawal,DriverIncident,DriverNominee,DriverInsurance,DriverInsuranceClaim,DriverOffer,DriverPartnerNotice,DriverPushDevice]:
            self.assertIsNone(self.db.scalar(select(model).where(model.driver_id==driver_id)))
        from backend.models_driver_agreement import DriverAgreementAcceptance
        audit=self.db.scalar(select(DriverAgreementAcceptance).where(DriverAgreementAcceptance.driver_temp_id==value['driver_temp_id']))
        self.assertTrue(audit.accepted);self.assertIsNone(audit.driver_id)

    def test_legacy_driver_without_partner_records(self):
        driver_id=self.user.id;admin_delete_user(self.db,driver_id)
        self.assertIsNone(self.db.get(Driver,driver_id));self.assertIsNone(self.db.get(User,driver_id))

    def test_rollback_does_not_remove_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            document=Path(directory)/'encrypted';document.write_bytes(b'encrypted')
            self.db.add(DriverDocument(driver_id=self.user.id,kind='selfie',encrypted_path=str(document),mime='image/jpeg'));self.db.flush()
            admin_delete_user(self.db,self.user.id)
            self.assertTrue(document.exists());self.db.rollback()
            self.assertNotIn('removed_drivers',self.db.info);self.assertTrue(document.exists())

    def test_committed_cleanup_only_removes_owned_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'driver-private'/str(self.user.id);parent.mkdir(parents=True)
            own=parent/'encrypted';own.write_bytes(b'encrypted');outside=Path(directory)/'other-driver';outside.write_bytes(b'keep')
            session=SimpleNamespace(info={'removed_drivers':[(self.user.id,[str(own),str(outside)])]})
            with patch.object(cleanup.settings,'file_root',directory),patch('backend.services.redis_geo_service.remove') as remove:
                cleanup.cleanup_after_commit(session)
                remove.assert_called_once_with(self.user.id)
            self.assertFalse(own.exists());self.assertTrue(outside.exists())


if __name__=='__main__':unittest.main()
