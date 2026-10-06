import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as SQLSession

from backend.db import engine, get_db
from backend.main import app
from backend.models import Order, User, Driver, Customer, Restaurant, SupportTicket
from backend.schemas import AdminUserCreate
from backend.services import operations_service
from backend.config import settings


class AdminPortalTest(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = SQLSession(bind=self.connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
        def dependency():
            yield self.db
            self.db.commit()
        app.dependency_overrides[get_db] = dependency
        self.client = TestClient(app,base_url='https://testserver')
        self.headers = {'X-Dashvanti-Admin-Secret': settings.admin_secret}
        self.people = {}
        for role in ('customer', 'restaurant', 'driver'):
            data = AdminUserCreate(role=role, email=f'admin-audit-{uuid4().hex}@example.com',
                                   password='audit-test-password', name=f'Admin audit {role}')
            row = operations_service.admin_create_user(self.db, data)
            self.people[role] = row['id']
        self.order = Order(customer_id=self.people['customer'], restaurant_id=self.people['restaurant'],
                           driver_id=None, request_key=uuid4().hex, mode='delivery', address='Test',
                           status='PLACED', total=Decimal('25'), delivery_fee=Decimal('3'))
        self.db.add(self.order)
        self.db.commit()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def get(self, path):
        return self.client.get('/api'+path, headers=self.headers)

    def post(self, path, data=None):
        return self.client.post('/api'+path, headers=self.headers, json=data)

    def test_all_menu_read_apis_and_authentication(self):
        paths=['/operations/admin/users', '/operations/admin/promotions', '/content/home',
               '/operations/tickets/all', '/operations/audit', '/operations/funds',
               '/operations/funds/revenue', '/operations/cancellation-policy',
               '/operations/admin/notifications', '/operations/admin/navigation-state',
               f'/operations/admin/orders/{self.order.id}/messages',
               f'/operations/orders/{self.order.id}/nearby-drivers']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 200)
                if not path.startswith('/content/'):
                    self.assertIn(self.client.get('/api'+path).status_code, (401,403))

    def test_user_update_and_permanent_delete(self):
        for role, model in [('customer', Customer), ('restaurant', Restaurant), ('driver', Driver)]:
            uid=self.people[role]
            response=self.client.put(f'/api/operations/admin/users/{uid}',headers=self.headers,
                                     json={'name':'Changed audit name'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.db.get(User,uid).name,'Changed audit name')
            response=self.client.delete(f'/api/operations/admin/users/{uid}',headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertIsNone(self.db.get(User,uid))
            self.assertIsNone(self.db.get(model,uid))

    def test_manual_assignment_status_and_chat(self):
        response=self.post(f'/operations/orders/{self.order.id}/reassign',
                           {'driver_id':self.people['driver'],'expected_driver_id':None,'reason':'Audit assignment'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.db.get(Order,self.order.id).driver_id,self.people['driver'])
        response=self.post(f'/operations/orders/{self.order.id}/status?status=ACCEPTED')
        self.assertEqual(response.status_code,200,response.text)
        response=self.post(f'/operations/admin/orders/{self.order.id}/messages',{'body':'Audit support reply'})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(self.get(f'/operations/admin/orders/{self.order.id}/messages').json()[-1]['body'],'Audit support reply')
        self.assertEqual(self.get('/operations/admin/notifications').status_code,200)

    def test_unpaid_order_cannot_be_dispatched(self):
        for status in ['PAYMENT_PENDING','PAYMENT_FAILED','SANDBOX_PAID']:
            self.order.status=status
            self.db.commit()
            self.assertEqual(self.post(f'/operations/orders/{self.order.id}/status?status=ACCEPTED').status_code,409)

    def test_banner_support_and_cancellation_policy(self):
        response=self.client.put('/api/content/banner',headers=self.headers,
                                 json={'title':'Audit banner','description':'Audit only','enabled':False})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.get('/content/home').json()['banner']['title'],'Audit banner')
        ticket=SupportTicket(user_id=self.people['customer'],subject='Audit support',description='Temporary audit ticket')
        self.db.add(ticket)
        self.db.commit()
        response=self.client.put(f'/api/operations/tickets/{ticket.id}',headers=self.headers,
                                 json={'status':'resolved','resolution':'Audit resolved'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.db.get(SupportTicket,ticket.id).status,'resolved')
        response=self.client.put('/api/operations/cancellation-policy',headers=self.headers,
                                 json={'preparation_percent':75,'review_threshold':4})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.get('/operations/cancellation-policy').json()['review_threshold'],4)

    def test_disabled_promotion_is_manageable_and_duplicate_rejected(self):
        code='AUDIT'+uuid4().hex[:16]
        payload={'title':'Audit promotion','description':'Temporary','code':code,'percent':10,
                 'minimum':0,'cap':0,'enabled':False}
        response=self.post('/content/promotions',payload)
        self.assertEqual(response.status_code,201,response.text)
        pid=response.json()['id']
        self.assertTrue(any(row['id']==pid for row in self.get('/operations/admin/promotions').json()))
        self.assertFalse(any(row['id']==pid for row in self.get('/content/home').json()['promotions']))
        self.assertEqual(self.post('/content/promotions',payload).status_code,409)
        self.assertEqual(self.client.delete(f'/api/content/promotions/{pid}',headers=self.headers).status_code,200)

    def test_refund_and_pricing_database_actions(self):
        response=self.client.put('/api/operations/funds/rules/refund_limit',headers=self.headers,
                                 json={'method':'percent','value':100,'minimum':0,'enabled':True})
        self.assertEqual(response.status_code,200,response.text)
        response=self.post('/operations/funds/refunds',{'order_id':self.order.id,'amount':5,'reason':'Audit refund'})
        self.assertEqual(response.status_code,201,response.text)
        rid=response.json()['id']
        response=self.client.put('/api/operations/funds/refunds/'+rid,headers=self.headers,
                                 json={'order_id':self.order.id,'amount':4,'reason':'Audit updated refund'})
        self.assertEqual(response.status_code,200,response.text)
        rid=response.json()['id']
        self.assertEqual(self.client.delete('/api/operations/funds/refunds/'+rid,headers=self.headers).status_code,200)
        self.assertEqual(self.client.put('/api/operations/funds/rules/tax',headers=self.headers,
                                        json={'method':'percent','value':101}).status_code,422)

    def test_payout_record_and_duplicate_prevention(self):
        self.order.status='DELIVERED'
        self.db.commit()
        from backend.services.finance_service import breakdown, terms
        payload={'order_id':self.order.id,'payee_role':'restaurant','mode':'manual',
                 'confirmation':'AUDIT-BANK-REFERENCE','expected_amount':str(breakdown(self.order,0,terms(self.db,self.order))['restaurant_payout'])}
        response=self.post('/operations/funds/quick-pay',payload)
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(self.post('/operations/funds/quick-pay',payload).status_code,409)
        self.order.currency='INR'
        self.db.commit()
        self.assertEqual(self.post('/operations/funds/quick-pay',payload).status_code,409)


if __name__=='__main__':
    unittest.main()
