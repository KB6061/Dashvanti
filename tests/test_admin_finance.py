import unittest
from decimal import Decimal
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select
import test_admin_portal as fixtures
from backend.models import Order, PayoutTransaction, SystemConfig
from backend.payout_schemas import PayoutInput, PayoutRecipientInput, PayoutSettingsInput
from backend.services import finance_service as finance, payout_service as payout, revenue_service as revenue


class AdminFinanceTest(unittest.TestCase):
    setUp=fixtures.AdminPortalTest.setUp
    tearDown=fixtures.AdminPortalTest.tearDown

    def prepare(self):
        self.order.status='DELIVERED'
        self.order.total=Decimal('100')
        self.order.tax=Decimal('5')
        self.order.service_fee=Decimal('10')
        self.order.delivery_fee=Decimal('3')
        self.order.tip=Decimal('2')
        self.order.driver_id=self.people['driver']
        self.db.commit()

    def payload(self,role='restaurant',mode='manual'):
        amount=finance.breakdown(self.order,0,finance.terms(self.db,self.order))[role+'_payout']
        return PayoutInput(order_id=self.order.id,payee_role=role,mode=mode,confirmation='AUDIT-BANK-CONFIRMATION',expected_amount=amount)

    def stripe_settings(self,environment='test'):
        payout.save_settings(self.db,PayoutSettingsInput(automated_enabled=True,environment=environment,
                              secret_key='sk_'+environment+'_audit_not_real',confirm_live=environment=='live'))
        self.db.add(SystemConfig(key=f'payout:recipient:{environment}:{self.people["restaurant"]}',value='acct_AuditRecipient'))
        self.db.commit()

    def transfer(self,live=False):
        return {'id':'tr_AuditReference','amount':int(self.payload().expected_amount*100),'currency':'usd',
                'destination':'acct_AuditRecipient','livemode':live,'amount_reversed':0}

    def test_breakdown_reconciles_and_does_not_commission_tax_tip_fees(self):
        self.prepare()
        values=finance.breakdown(self.order,0,{'method':'percent','value':'15','enabled':True})
        self.assertEqual(values['commission'],Decimal('12.00'))
        self.assertEqual(values['restaurant_payout'],Decimal('68.00'))
        self.assertEqual(values['driver_payout'],Decimal('5.00'))
        self.assertEqual(values['platform_profit'],Decimal('22.00'))
        self.assertEqual(sum(values[k] for k in ['driver_payout','restaurant_payout','tax','platform_profit','refund_amount']),values['order_amount'])
        refunded=finance.breakdown(self.order,25,{'method':'percent','value':'15','enabled':True})
        self.assertEqual(sum(refunded[k] for k in ['driver_payout','restaurant_payout','tax','platform_profit','refund_amount']),Decimal('100'))
        self.order.tax=Decimal('50');self.order.service_fee=0;self.order.delivery_fee=0;self.order.tip=0
        final_cent=finance.breakdown(self.order,'99.99',{'method':'percent','value':'0','enabled':True})
        self.assertGreaterEqual(final_cent['platform_profit'],0)
        self.assertEqual(sum(final_cent[k] for k in ['driver_payout','restaurant_payout','tax','platform_profit','refund_amount']),Decimal('100'))

    def test_summary_excludes_active_unpaid_test_cancelled_and_inr(self):
        self.prepare()
        baseline=revenue.summary_cards(self.db)['lifetime']
        for status,currency in [('ACCEPTED','USD'),('PAYMENT_PENDING','USD'),('SANDBOX_PAID','USD'),('CANCELLED','USD'),('DELIVERED','INR')]:
            self.order.status=status;self.order.currency=currency;self.db.commit()
            self.assertEqual(revenue.summary_cards(self.db)['lifetime'],baseline-100)

    def test_commission_is_frozen_and_disabled_or_flat_rule_is_respected(self):
        self.prepare()
        first=finance.terms(self.db,self.order)
        config=self.db.get(SystemConfig,'fund:restaurant_commission')
        if config:config.value='{"method":"percent","value":99,"enabled":true}'
        else:self.db.add(SystemConfig(key='fund:restaurant_commission',value='{"method":"percent","value":99,"enabled":true}'))
        self.db.commit()
        self.assertEqual(finance.terms(self.db,self.order),first)
        self.assertEqual(finance.breakdown(self.order,0,{'method':'flat','value':'7','enabled':True})['commission'],7)
        self.assertEqual(finance.breakdown(self.order,0,{'method':'flat','value':'7','enabled':False})['commission'],0)

    def test_manual_receipt_persists_reference_and_prevents_duplicates(self):
        self.prepare()
        for role in ('driver','restaurant'):
            data=self.payload(role)
            result=payout.send(self.db,data)
            self.assertEqual(result['status'],'PAID')
            self.assertEqual(result['confirmation'],'AUDIT-BANK-CONFIRMATION')
            self.assertIsNotNone(self.db.get(PayoutTransaction,result['id']))
            self.assertEqual(payout.receipt(self.db,self.db.get(PayoutTransaction,result['id']))['reference'],result['reference'])
            with self.assertRaises(HTTPException) as exc:payout.send(self.db,data)
            self.assertEqual(exc.exception.status_code,409)

    def test_test_transfer_does_not_settle_real_balance(self):
        self.prepare();self.stripe_settings()
        with patch.object(payout,'stripe',return_value=self.transfer()) as provider:
            result=payout.send(self.db,self.payload(mode='stripe'))
        self.assertEqual(result['status'],'TEST_TRANSFERRED')
        self.assertEqual(result['provider_reference'],'tr_AuditReference')
        self.assertEqual(result['confirmation'],'')
        self.assertEqual(revenue.payout_map(self.db).get((self.order.id,'restaurant'),0),0)
        self.assertEqual(provider.call_args.args[-1],result['reference'])
        self.assertEqual(payout.send(self.db,self.payload())['status'],'PAID')

    def test_uncertain_transfer_reserves_balance_and_reuses_reference(self):
        self.prepare();self.stripe_settings('live')
        with patch.object(payout,'stripe',side_effect=HTTPException(503,'Timeout')):
            result=payout.send(self.db,self.payload(mode='stripe'))
        self.assertEqual(result['status'],'UNKNOWN')
        with self.assertRaises(HTTPException):payout.send(self.db,self.payload())
        with patch.object(payout,'stripe',return_value=self.transfer(True)) as provider:
            final=payout.reconcile(self.db,result['id'])
        self.assertEqual(final['status'],'TRANSFERRED')
        self.assertEqual(final['reference'],result['reference'])
        self.assertEqual(provider.call_args.args[-1],result['reference'])
        self.assertEqual(revenue.payout_map(self.db)[(self.order.id,'restaurant')],self.payload().expected_amount)

    def test_mismatched_transfer_is_not_counted_paid_and_secrets_are_redacted(self):
        self.prepare();self.stripe_settings()
        self.assertNotIn('secret_key',payout.settings_view(self.db))
        bad=self.transfer();bad['amount']=1
        with patch.object(payout,'stripe',return_value=bad):
            result=payout.send(self.db,self.payload(mode='stripe'))
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(revenue.payout_map(self.db).get((self.order.id,'restaurant'),0),0)

    def test_provider_settings_and_recipient_controls(self):
        self.prepare()
        with self.assertRaises(HTTPException):payout.save_settings(self.db,PayoutSettingsInput(automated_enabled=True))
        self.stripe_settings()
        with patch.object(payout,'stripe',return_value={'payouts_enabled':True,'capabilities':{'transfers':'active'}}):
            self.assertEqual(payout.save_recipient(self.db,PayoutRecipientInput(user_id=self.people['driver'],account_id='acct_AuditDriver'))['account_id'],'acct_AuditDriver')
        payout.save_settings(self.db,PayoutSettingsInput(manual_enabled=False))
        with self.assertRaises(HTTPException):payout.send(self.db,self.payload())


if __name__=='__main__':unittest.main()
