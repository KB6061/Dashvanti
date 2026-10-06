import hashlib
import json
import os
import time
import unittest
import logging
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session as TestSession
from backend.db import engine, get_db
from backend.main import app
from backend.models import User, Customer, Restaurant, MenuItem, CartItem, Order
from backend.payment_models import Payment, Refund, PaymentMethod, AdminSettings, PaymentEvent
from backend.services import admin_payment_service as admin, phonepe_service as pg
from backend.services.session_service import issue_tokens
from backend.services.geo_service import detect_country
from backend.config import settings
from backend.payment_schemas import SettingsInput
from backend.utils.signature import encode_payload, x_verify, verify_sha_webhook

logging.disable(logging.CRITICAL)


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = TestSession(bind=self.connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
        suffix = uuid.uuid4().hex
        self.user = User(email=f'pg-test-{suffix}@example.com', password='unused', role='customer', name='PG transaction test', country='IN')
        self.restaurant_user = User(email=f'pg-restaurant-{suffix}@example.com', password='unused', role='restaurant', name='PG restaurant test')
        self.db.add_all([self.user, self.restaurant_user])
        self.db.flush()
        self.restaurant = Restaurant(id=self.restaurant_user.id, name='PG test restaurant', is_open=True, currency='INR')
        self.db.add_all([Customer(id=self.user.id), self.restaurant])
        self.db.flush()
        self.menu = MenuItem(restaurant_id=self.restaurant.id, name='PG test meal', price=Decimal('100.00'), available=True)
        self.db.add(self.menu)
        self.db.flush()
        self.db.add(CartItem(customer_id=self.user.id, menu_item_id=self.menu.id, quantity=1))
        self.cfg = {'client_id': 'TEST_CLIENT', 'client_secret': 'TEST_SECRET', 'client_version': 1,
            'webhook_username': 'test_hook', 'webhook_password': 'TEST_HOOK_SECRET'}
        row = AdminSettings(environment='sandbox', api_version='v2', encrypted_credentials=admin.cipher().encrypt(json.dumps(self.cfg).encode()).decode())
        self.db.add(row)
        self.db.flush()
        method = self.db.get(PaymentMethod, 'phonepe')
        method.enabled = True
        method.settings_id = row.id
        self.db.commit()
        def database():
            try:
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app, base_url='https://customer.dashvanti.com')
        self.client.headers['Authorization'] = 'Bearer ' + issue_tokens(self.user)['access_token']
        self.key = uuid.uuid4().hex
        self.body = {'checkout': {'mode': 'pickup', 'request_key': self.key, 'tip': '0'}, 'instrument': 'UPI'}
        self.pay_patcher = patch.object(pg.Gateway, 'pay', return_value={'orderId': 'OMO_TEST', 'state': 'PENDING', 'expireAt': int((time.time()+1200)*1000), 'redirectUrl': 'https://mercury-uat.phonepe.com/transact/uat_v2?token=TEST'})
        self.pay_mock = self.pay_patcher.start()
        self.background = patch.object(pg, 'reconcile').start()

    def tearDown(self):
        patch.stopall()
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def pay(self):
        response = self.client.post('/api/phonepe/pay', json=self.body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def completed(self, payment):
        with patch.object(pg.Gateway, 'status', return_value={'orderId': 'OMO_TEST', 'state': 'COMPLETED', 'amount': payment['amount']}):
            result = self.client.post('/api/phonepe/status', json={'transaction_id': payment['id']})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_country_gate_and_direct_order_bypass(self):
        for country in ['US', None, 'GB']:
            self.user.country = country
            self.db.commit()
            methods = self.client.get('/api/payment/methods').json()['methods']
            self.assertNotIn('phonepe', [row['id'] for row in methods])
            result = self.client.post('/api/phonepe/pay', json=self.body)
            self.assertEqual(result.status_code, 403)
        self.user.country = 'IN'
        self.db.commit()
        self.assertIn('phonepe', [row['id'] for row in self.client.get('/api/payment/methods').json()['methods']])
        result = self.client.post('/api/orders', json={**self.body['checkout'], 'payment_mode': 'PhonePe'})
        self.assertEqual(result.status_code, 400)

    def test_incomplete_and_disabled_gateway_hidden(self):
        method = self.db.get(PaymentMethod, 'phonepe')
        method.enabled = False
        self.db.commit()
        self.assertEqual(len(self.client.get('/api/payment/methods').json()['methods']), 1)
        self.assertEqual(self.client.post('/api/phonepe/pay', json=self.body).status_code, 503)

    def test_untrusted_ip_country_headers_fail_closed(self):
        request = SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'), headers={'cf-ipcountry': 'IN', 'x-forwarded-for': '1.1.1.1', 'x-dashvanti-client-ip': '1.1.1.1', 'x-dashvanti-ip-time': str(int(time.time())), 'x-dashvanti-ip-signature': 'forged'})
        self.assertIsNone(detect_country(request, SimpleNamespace(country=None)))

    def test_amount_is_server_calculated_and_idempotent(self):
        payment = self.pay()
        orders = list(self.db.scalars(select(Order).where(Order.id.in_(payment['order_ids']))))
        self.assertEqual(payment['amount'], int(sum(row.total for row in orders)*100))
        self.assertEqual(orders[0].status, 'PAYMENT_PENDING')
        again = self.pay()
        self.assertEqual(payment['id'], again['id'])
        self.assertEqual(self.pay_mock.call_count, 1)
        forged = self.client.post('/api/phonepe/pay', json={**self.body, 'amount': 1})
        self.assertEqual(forged.status_code, 422)

    def test_usd_cannot_be_charged_as_inr(self):
        self.restaurant.currency = 'USD'
        self.db.commit()
        result = self.client.post('/api/phonepe/pay', json=self.body)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.pay_mock.call_count, 0)

    def test_success_mismatch_and_sandbox_dispatch_guard(self):
        payment = self.pay()
        with patch.object(pg.Gateway, 'status', return_value={'orderId': 'OMO_TEST', 'state': 'COMPLETED', 'amount': 1}):
            self.assertEqual(self.client.post('/api/phonepe/status', json={'transaction_id': payment['id']}).status_code, 502)
        self.assertEqual(self.db.get(Order, payment['order_ids'][0]).status, 'PAYMENT_PENDING')
        self.completed(payment)
        self.assertEqual(self.db.get(Order, payment['order_ids'][0]).status, 'SANDBOX_PAID')
        with patch.object(pg.Gateway, 'status', return_value={'state': 'PENDING'}):
            response = self.client.post('/api/phonepe/status', json={'transaction_id': payment['id']})
        self.assertEqual(response.json()['status'], 'COMPLETED')

    def test_production_success_releases_order_once(self):
        payment = self.pay()
        row = self.db.get(Payment, payment['id'])
        row.environment = 'production'
        self.db.commit()
        with patch('backend.services.kafka_event_service.emit') as emit:
            self.completed(payment)
            self.completed(payment)
        self.assertEqual(emit.call_count, 1)
        self.assertEqual(self.db.get(Order, payment['order_ids'][0]).status, 'PLACED')

    def test_unknown_request_is_not_double_charged(self):
        self.pay_mock.side_effect = HTTPException(502, 'timeout')
        self.assertEqual(self.client.post('/api/phonepe/pay', json=self.body).status_code, 502)
        row = self.db.scalar(select(Payment).where(Payment.request_key == f'{self.user.id}:{self.key}'))
        self.assertEqual(row.status, 'UNKNOWN')
        self.assertEqual(self.pay()['id'], row.id)
        self.assertEqual(self.pay_mock.call_count, 1)

    def test_callback_authenticated_deduplicated_and_not_trusted_as_success(self):
        payment = self.pay()
        callback = {'event': 'checkout.order.completed', 'payload': {'merchantOrderId': payment['merchant_order_id'], 'state': 'COMPLETED', 'amount': payment['amount']}}
        response = self.client.post('/api/phonepe/callback', json=callback, headers={'Authorization': 'forged'})
        self.assertEqual(response.status_code, 401)
        signature = hashlib.sha256(b'test_hook:TEST_HOOK_SECRET').hexdigest()
        for _ in range(2):
            response = self.client.post('/api/phonepe/callback', json=callback, headers={'Authorization': signature})
            self.assertEqual(response.status_code, 200, response.text)
        count = self.db.scalar(select(func.count()).select_from(PaymentEvent).where(PaymentEvent.payment_id == payment['id'], PaymentEvent.event == 'callback_received'))
        self.assertEqual(count, 1)
        self.assertEqual(self.db.get(Payment, payment['id']).status, 'PENDING')
        self.background.assert_called_with(payment['id'], None)

    def test_refund_reservation_idempotency_and_verification(self):
        payment = self.pay()
        self.completed(payment)
        headers = {'X-Dashvanti-Admin-Secret': settings.admin_secret}
        data = {'amount': 100, 'reason': 'Test partial refund', 'request_key': uuid.uuid4().hex}
        with patch.object(pg.Gateway, 'refund', return_value={'refundId': 'OMR_TEST', 'state': 'PENDING'}) as gateway:
            response = self.client.post(f"/api/admin/payment/refund/{payment['id']}", json=data, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            again = self.client.post(f"/api/admin/payment/refund/{payment['id']}", json=data, headers=headers)
            self.assertEqual(response.json()['id'], again.json()['id'])
            self.assertEqual(gateway.call_count, 1)
            excessive = {**data, 'request_key': uuid.uuid4().hex, 'amount': payment['amount']}
            self.assertEqual(self.client.post(f"/api/admin/payment/refund/{payment['id']}", json=excessive, headers=headers).status_code, 409)
        refund = response.json()
        with patch.object(pg.Gateway, 'refund_status', return_value={'state': 'COMPLETED', 'refundId': 'OMR_TEST', 'amount': 100, 'originalMerchantOrderId': payment['merchant_order_id']}):
            checked = self.client.post(f"/api/admin/payment/refund/{refund['id']}/status", headers=headers)
        self.assertEqual(checked.json()['status'], 'COMPLETED')

    def test_customer_cannot_refund_or_read_admin_or_other_customer_payment(self):
        payment = self.pay()
        for path in ['/api/admin/payment/settings','/api/admin/payment/transactions','/api/admin/payment/settlements','/api/admin/payment/logs']:
            self.assertEqual(self.client.get(path).status_code, 403)
        data = {'transaction_id': payment['id'], 'amount': 100, 'reason': 'unauthorized', 'request_key': uuid.uuid4().hex}
        self.assertEqual(self.client.post('/api/phonepe/refund', json=data).status_code, 403)
        stranger = User(email=f'pg-stranger-{uuid.uuid4().hex}@example.com', password='unused', role='customer', name='PG stranger test')
        self.db.add(stranger)
        self.db.commit()
        response = self.client.post('/api/phonepe/status', json={'transaction_id': payment['id']}, headers={'Authorization': 'Bearer '+issue_tokens(stranger)['access_token']})
        self.assertEqual(response.status_code, 404)

    def test_credentials_redacted_encrypted_and_logged_without_secrets(self):
        headers = {'X-Dashvanti-Admin-Secret': settings.admin_secret}
        view = self.client.get('/api/admin/payment/settings', headers=headers)
        self.assertNotIn('TEST_SECRET', view.text)
        self.assertTrue(view.json()['credentials']['client_secret'])
        row = admin.active_settings(self.db)
        self.assertNotIn('TEST_SECRET', row.encrypted_credentials)
        self.pay()
        export = self.client.get('/api/admin/payment/logs', headers=headers)
        self.assertNotIn('TEST_SECRET', export.text)
        self.assertNotIn('redirect_url', export.text)
        self.assertIn('transactions', export.json())

    def test_signatures_and_v2_oauth_payload(self):
        self.pay_patcher.stop()
        encoded = encode_payload({'amount': 100})
        expected = hashlib.sha256((encoded+'/pg/v1/pay'+'SALT').encode()).hexdigest()+'###1'
        self.assertEqual(x_verify(encoded, '/pg/v1/pay', 'SALT', 1), expected)
        self.assertFalse(verify_sha_webhook('forged', 'u', 'p'))
        gateway = pg.Gateway(admin.active_settings(self.db))
        pg.TOKEN_CACHE.clear()
        with patch('backend.services.phonepe_service.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = httpx.Response(200, json={'access_token':'TEST_AUTH_TOKEN','expires_at':int(time.time()+600)})
            client.return_value.__enter__.return_value.request.return_value = httpx.Response(200, json={'state':'PENDING'})
            payment = SimpleNamespace(id=123, user_id=self.user.id, merchant_order_id='DV_TEST', amount=100)
            gateway.pay(payment, 'UPI_INTENT')
            call = client.return_value.__enter__.return_value.request.call_args
            self.assertEqual(call.kwargs['headers']['Authorization'], 'O-Bearer TEST_AUTH_TOKEN')
            self.assertEqual(call.kwargs['json']['amount'], 100)
            self.assertEqual(call.kwargs['json']['paymentFlow']['paymentModeConfig']['enabledPaymentModes'], [{'type':'UPI_INTENT'}])

    def test_admin_settings_rotation_preserves_original_transaction_credentials(self):
        payment = self.pay()
        original_id = self.db.get(Payment, payment['id']).settings_id
        headers = {'X-Dashvanti-Admin-Secret': settings.admin_secret}
        response = self.client.post('/api/admin/payment/settings/update', json={
            'environment':'sandbox', 'api_version':'v2', 'client_id':'NEW_CLIENT', 'client_secret':'NEW_SECRET'}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(admin.credentials(admin.active_settings(self.db))['client_secret'], 'NEW_SECRET')
        self.assertEqual(admin.credentials(self.db.get(AdminSettings, original_id))['client_secret'], 'TEST_SECRET')
        blank = self.client.post('/api/admin/payment/settings/update', json={'environment':'sandbox', 'api_version':'v2', 'client_secret':''}, headers=headers)
        self.assertEqual(blank.status_code, 200)
        self.assertEqual(admin.credentials(admin.active_settings(self.db))['client_secret'], 'NEW_SECRET')
        live = self.client.post('/api/admin/payment/settings/update', json={'environment':'production','api_version':'v2'}, headers=headers)
        self.assertEqual(live.status_code, 400)

    def test_toggle_other_gateways_does_not_offer_unconfigured_charges(self):
        headers = {'X-Dashvanti-Admin-Secret': settings.admin_secret}
        for method in ('razorpay', 'cashfree'):
            response = self.client.post('/api/admin/payment/methods/toggle', json={'method':method,'enabled':True}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['enabled'])
            self.assertFalse(response.json()['configured'])
        allowed = [row['id'] for row in self.client.get('/api/payment/methods').json()['methods']]
        self.assertNotIn('razorpay', allowed)
        self.assertNotIn('cashfree', allowed)

    def test_failed_payment_and_refund_timeout_recovery(self):
        payment = self.pay()
        with patch.object(pg.Gateway,'status',return_value={'orderId':'OMO_TEST','state':'FAILED'}):
            failed = self.client.post('/api/phonepe/status',json={'transaction_id':payment['id']})
        self.assertEqual(failed.json()['status'],'FAILED')
        self.assertEqual(self.db.get(Order,payment['order_ids'][0]).status,'PAYMENT_FAILED')
        self.completed(payment)
        headers = {'X-Dashvanti-Admin-Secret':settings.admin_secret}
        data = {'amount':100,'reason':'Uncertain test refund','request_key':uuid.uuid4().hex}
        with patch.object(pg.Gateway,'refund',side_effect=HTTPException(502,'timeout')) as outgoing:
            first = self.client.post(f"/api/admin/payment/refund/{payment['id']}",json=data,headers=headers)
            self.assertEqual(first.status_code,502)
            again = self.client.post(f"/api/admin/payment/refund/{payment['id']}",json=data,headers=headers)
            self.assertEqual(again.json()['status'],'UNKNOWN')
            self.assertEqual(outgoing.call_count,1)

    def test_settlement_import_is_authenticated_and_identifies_report_source(self):
        headers = {'X-Dashvanti-Admin-Secret':settings.admin_secret}
        data = {'reference':'PG_TEST_'+uuid.uuid4().hex,'environment':'sandbox','amount':100,'status':'SETTLED'}
        self.assertEqual(self.client.post('/api/admin/payment/settlements/import',json=data).status_code,403)
        self.assertEqual(self.client.post('/api/admin/payment/settlements/import',json=data,headers=headers).status_code,200)
        response = self.client.get('/api/admin/payment/settlements',headers=headers)
        self.assertEqual(response.json()['items'][0]['source'],'merchant_report')
        self.assertEqual(response.json()['items'][0]['reference'],data['reference'])

    def test_inr_payment_orders_do_not_inflate_dollar_revenue(self):
        payment = self.pay()
        from backend.services.revenue_service import revenue_report
        report = revenue_report(self.db, {})
        self.assertFalse(any(row['order_id'] in payment['order_ids'] for row in report['rows']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
