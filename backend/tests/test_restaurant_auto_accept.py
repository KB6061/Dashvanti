import secrets
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select, func
from backend.db import Session
from backend.models import User, Customer, Restaurant, Driver, Order, DeliveryStatus, Notification, MenuItem, CartItem, Address, now
from backend.models_driver_partner import DriverOffer
from backend.schemas import Checkout
from backend.services import restaurant_auto_accept_service as service, order_service, delivery_service


class RestaurantAutoAcceptTests(unittest.TestCase):
    def setUp(self):
        self.db=Session()
        self.customer=User(name='Auto audit customer',email='auto-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='customer')
        self.restaurant=User(name='Auto audit restaurant',email='auto-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='restaurant')
        self.driver=User(name='Auto audit driver',email='auto-audit-'+secrets.token_hex(8)+'@example.com',password='x',role='driver')
        self.db.add_all([self.customer,self.restaurant,self.driver]);self.db.flush()
        self.db.add_all([Customer(id=self.customer.id),Restaurant(id=self.restaurant.id,name='Auto audit',address='Audit restaurant address',is_open=True,country='US',currency='USD',latitude=36.15,longitude=-86.78),Driver(id=self.driver.id,online=True)]);self.db.flush()
        self.candidate={'id':self.driver.id,'distance_miles':1,'drive_minutes':4,'distance_type':'driving'}

    def tearDown(self):
        self.db.rollback();self.db.close()

    def order(self, status='PLACED', mode='delivery', payment_mode='Cash'):
        row=Order(customer_id=self.customer.id,restaurant_id=self.restaurant.id,request_key=secrets.token_hex(16),status=status,mode=mode,payment_mode=payment_mode,currency='USD',address='Audit delivery address',total=Decimal(20),delivery_fee=Decimal(5))
        self.db.add(row);self.db.flush();self.db.add(DeliveryStatus(order_id=row.id,status=status));self.db.flush();return row

    def test_cash_checkout_accepts_then_driver_must_accept(self):
        menu=MenuItem(restaurant_id=self.restaurant.id,name='Audit meal',price=Decimal(10));address=Address(customer_id=self.customer.id,label='Audit',details='Audit delivery address',country='US',state='Tennessee',city='Nashville',latitude=36.16,longitude=-86.77)
        self.db.add_all([menu,address]);self.db.flush();self.db.add(CartItem(customer_id=self.customer.id,menu_item_id=menu.id,quantity=1));self.db.flush()
        data=Checkout(mode='delivery',payment_mode='Cash',address_id=address.id,request_key=secrets.token_hex(16))
        with patch('backend.services.eta_service.route',return_value={'distance_meters':1609.344,'distance_type':'driving'}),patch('backend.services.store_status_service.accepting',return_value=True),patch('backend.services.dispatch_service.nearby',return_value=[self.candidate]):
            result=order_service.checkout(self.db,self.customer,data)
        order=self.db.get(Order,result['id']);self.assertEqual(order.status,'ACCEPTED');self.assertIsNone(order.driver_id)
        offer=self.db.scalar(select(DriverOffer).where(DriverOffer.order_id==order.id));self.assertEqual(offer.driver_id,self.driver.id);self.assertEqual(offer.status,'OFFERED')
        self.assertIsNotNone(self.db.scalar(select(Notification.id).where(Notification.user_id==self.driver.id,Notification.order_id==order.id,Notification.kind=='delivery-offer')))
        with patch('backend.services.dispatch_service.eligible',return_value=self.candidate):delivery_service.accept(self.db,self.driver,order.id)
        self.assertEqual(order.driver_id,self.driver.id);self.assertEqual(offer.status,'ACCEPTED')

    def test_repeated_acceptance_does_not_duplicate_offers(self):
        order=self.order()
        with patch('backend.services.dispatch_service.nearby',return_value=[self.candidate]):
            self.assertTrue(service.accept_order(self.db,order));self.assertFalse(service.accept_order(self.db,order))
        self.assertEqual(self.db.scalar(select(func.count(DriverOffer.id)).where(DriverOffer.order_id==order.id)),1)
        self.assertEqual(self.db.scalar(select(func.count(DeliveryStatus.id)).where(DeliveryStatus.order_id==order.id,DeliveryStatus.status=='ACCEPTED')),1)

    def test_no_driver_keeps_accepted_order_unassigned(self):
        order=self.order()
        with patch('backend.services.dispatch_service.nearby',return_value=[]):self.assertTrue(service.accept_order(self.db,order))
        self.assertEqual(order.status,'ACCEPTED');self.assertIsNone(order.driver_id)
        self.assertIsNone(self.db.scalar(select(DriverOffer.id).where(DriverOffer.order_id==order.id)))

    def test_pickup_is_accepted_without_driver_request(self):
        order=self.order(mode='pickup')
        with patch('backend.services.dispatch_service.nearby') as nearby:self.assertTrue(service.accept_order(self.db,order));nearby.assert_not_called()
        self.assertIsNone(order.driver_id)

    def test_unpaid_failed_sandbox_and_scheduled_are_not_dispatched(self):
        with patch('backend.services.dispatch_service.nearby') as nearby:
            for status in ['PAYMENT_PENDING','PAYMENT_FAILED','SANDBOX_PAID','SCHEDULED','CANCELLED','DELIVERED']:
                order=self.order(status=status);self.assertFalse(service.accept_order(self.db,order));self.assertEqual(order.status,status)
            order=self.order(payment_mode='PhonePe');self.assertFalse(service.accept_order(self.db,order));self.assertEqual(order.status,'PLACED')
            nearby.assert_not_called()

    def test_verified_production_payment_accepts_but_sandbox_does_not(self):
        from backend.payment_models import Payment, PaymentOrder, AdminSettings
        from backend.services.phonepe_service import apply_status
        for environment,expected in [('production','ACCEPTED'),('sandbox','SANDBOX_PAID')]:
            order=self.order(status='PAYMENT_PENDING',payment_mode='PhonePe')
            cfg=AdminSettings(environment=environment,api_version='v2',encrypted_credentials='');self.db.add(cfg);self.db.flush()
            payment=Payment(user_id=self.customer.id,settings_id=cfg.id,merchant_order_id='audit-'+secrets.token_hex(12),request_key=secrets.token_hex(12),amount=2000,currency='INR',country='IN',environment=environment,api_version='v2',status='PENDING')
            self.db.add(payment);self.db.flush();self.db.add(PaymentOrder(payment_id=payment.id,order_id=order.id,original_order_id=order.id));self.db.flush()
            with patch('backend.services.dispatch_service.nearby',return_value=[]):apply_status(self.db,payment.id,{'state':'COMPLETED','orderId':'audit-'+secrets.token_hex(8),'amount':2000})
            self.assertEqual(order.status,expected)

    def test_scheduled_release_accepts_only_when_due(self):
        from backend.restaurant_experience_models import ScheduledOrder
        from backend.services.restaurant_experience_service import release_due
        order=self.order(status='SCHEDULED');schedule=ScheduledOrder(order_id=order.id,release_at=now()+timedelta(hours=1));self.db.add(schedule);self.db.flush()
        release_due(self.db,[order.id]);self.assertEqual(order.status,'SCHEDULED')
        schedule.release_at=now()-timedelta(seconds=1);self.db.flush()
        with patch('backend.services.store_status_service.accepting',return_value=True),patch('backend.services.dispatch_service.nearby',return_value=[]):release_due(self.db,[order.id])
        self.assertEqual(order.status,'ACCEPTED');self.assertTrue(schedule.released)


if __name__=='__main__':unittest.main()
