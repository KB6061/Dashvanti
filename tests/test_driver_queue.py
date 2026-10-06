import unittest
from unittest.mock import patch
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from backend.models import User,Order,Driver,DriverLocation,Restaurant,DeliveryStatus,now
from backend.models_driver_queue import DriverUpcomingOrder
from backend.services.auth_service import passwords
import test_admin_portal as fixtures

class DriverQueueTest(unittest.TestCase):
    setUp=fixtures.AdminPortalTest.setUp
    tearDown=fixtures.AdminPortalTest.tearDown

    def prepare(self):
        self.uid=self.people['driver'];user=self.db.get(User,self.uid);user.password=passwords.hash('QueueTestPassword1')
        self.db.get(Driver,self.uid).online=True;self.db.add(DriverLocation(driver_id=self.uid,latitude=19.125,longitude=72.999))
        self.db.get(Restaurant,self.people['restaurant']).address='Test restaurant address'
        self.order.driver_id=self.uid;self.order.status='ON_THE_WAY_TO_CUSTOMER';self.order.address='Current delivery destination'
        self.db.add(DeliveryStatus(order_id=self.order.id,status='ON_THE_WAY_TO_CUSTOMER'))
        self.next=Order(customer_id=self.people['customer'],restaurant_id=self.people['restaurant'],request_key=uuid4().hex,mode='delivery',address='Upcoming delivery address',status='READY_FOR_PICKUP',total=0,delivery_fee=0)
        self.db.add(self.next);self.db.commit()
        with patch('backend.services.auth_service.emit'):
            token=self.client.post('/api/auth/login',json={'email':user.email,'password':'QueueTestPassword1','role':'driver'}).json()['access_token']
        self.auth={'Authorization':'Bearer '+token}
        self.route_patch=patch('backend.services.eta_service.route',return_value={'drive_minutes':3,'distance_meters':1609.344,'distance_miles':1,'distance_type':'driving'});self.route_patch.start();self.addCleanup(self.route_patch.stop)

    def claim(self,order=None):
        return self.client.post(f'/api/delivery/{(order or self.next).id}/accept',headers=self.auth)

    def test_busy_driver_offer_accept_and_automatic_promotion(self):
        self.prepare()
        rows=self.client.get('/api/delivery/available',headers=self.auth).json();offer=next(row for row in rows if row['id']==self.next.id)
        self.assertTrue(offer['upcoming']);self.assertEqual(offer['address'],'Upcoming delivery address')
        self.assertEqual(offer['current_order_id'],self.order.id);self.assertEqual(offer['pickup_eta_minutes'],6);self.assertEqual(offer['delivery_eta_minutes'],9)
        response=self.claim();self.assertEqual(response.status_code,200,response.text);self.assertTrue(response.json()['queued'])
        self.assertEqual(self.db.get(DriverUpcomingOrder,self.uid).order_id,self.next.id);self.assertIsNone(self.next.driver_id)
        self.assertEqual(self.order.driver_id,self.uid);self.assertEqual(self.order.status,'ON_THE_WAY_TO_CUSTOMER')
        self.assertFalse(any(row['id']==self.next.id for row in self.client.get('/api/orders',headers=self.auth).json()))
        response=self.client.post(f'/api/orders/{self.order.id}/status',headers=self.auth,json={'status':'DELIVERED'})
        self.assertEqual(response.status_code,200,response.text);self.assertIsNone(self.db.get(DriverUpcomingOrder,self.uid));self.assertEqual(self.next.driver_id,self.uid)
        self.assertTrue(self.db.scalar(select(DeliveryStatus.id).where(DeliveryStatus.order_id==self.next.id,DeliveryStatus.status=='DRIVER_ASSIGNED')))

    def test_queue_capacity_other_driver_claim_and_rejection_keep_current_order(self):
        self.prepare();self.assertEqual(self.claim().status_code,200)
        second=Order(customer_id=self.people['customer'],restaurant_id=self.people['restaurant'],request_key=uuid4().hex,mode='delivery',address='Another destination',status='READY_FOR_PICKUP',total=0,delivery_fee=0);self.db.add(second);self.db.commit()
        self.assertEqual(self.claim(second).status_code,409);self.assertEqual(self.client.get('/api/delivery/available',headers=self.auth).json(),[])
        other=User(email=uuid4().hex+'@example.com',name='Other driver',role='driver',password=passwords.hash('QueueTestPassword1'));self.db.add(other);self.db.flush()
        self.db.add(Driver(id=other.id,online=True));self.db.add(DriverLocation(driver_id=other.id,latitude=19.125,longitude=72.999));self.db.commit()
        with patch('backend.services.auth_service.emit'):
            token=self.client.post('/api/auth/login',json={'email':other.email,'password':'QueueTestPassword1','role':'driver'}).json()['access_token']
        other_auth={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.post(f'/api/delivery/{self.next.id}/accept',headers=other_auth).status_code,409)
        self.assertFalse(any(row['id']==self.next.id for row in self.client.get('/api/delivery/available',headers=other_auth).json()))
        response=self.client.post(f'/api/delivery/{self.next.id}/reject',headers=self.auth)
        self.assertEqual(response.status_code,200,response.text);self.assertIsNone(self.db.get(DriverUpcomingOrder,self.uid))
        self.assertEqual(self.order.status,'ON_THE_WAY_TO_CUSTOMER');self.assertEqual(self.order.driver_id,self.uid)
        self.assertFalse(any(row['id']==self.next.id for row in self.client.get('/api/delivery/available',headers=self.auth).json()))

    def test_cancelled_upcoming_order_releases_queue_and_admin_completed_current_promotes(self):
        self.prepare();self.assertEqual(self.claim().status_code,200)
        response=self.client.post(f'/api/operations/orders/{self.next.id}/status?status=CANCELLED',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(self.client.get('/api/delivery/queue',headers=self.auth).json(),[])
        self.assertEqual(self.order.driver_id,self.uid)
        self.next.status='READY_FOR_PICKUP';self.db.commit();self.assertEqual(self.claim().status_code,200)
        self.client.post(f'/api/operations/orders/{self.order.id}/status?status=DELIVERED',headers=self.headers)
        self.assertEqual(self.client.get('/api/delivery/queue',headers=self.auth).json(),[]);self.assertEqual(self.next.driver_id,self.uid)

    def test_offers_require_recent_gps_and_verified_driving_distance(self):
        self.prepare();self.db.get(DriverLocation,self.uid).updated_at=now()-timedelta(minutes=3);self.db.commit()
        self.assertFalse(any(row['id']==self.next.id for row in self.client.get('/api/delivery/available',headers=self.auth).json()))
        self.db.get(DriverLocation,self.uid).updated_at=now();self.db.commit()
        for travel in [{'drive_minutes':10,'distance_meters':1609.344,'distance_miles':1,'distance_type':'estimated'},{'drive_minutes':30,'distance_meters':18000,'distance_miles':11.18,'distance_type':'driving'}]:
            with patch('backend.services.eta_service.route',return_value=travel):
                self.assertFalse(any(row['id']==self.next.id for row in self.client.get('/api/delivery/available',headers=self.auth).json()))
        self.assertIn(self.client.get('/api/delivery/queue').status_code,(401,403))

if __name__=='__main__':unittest.main()
