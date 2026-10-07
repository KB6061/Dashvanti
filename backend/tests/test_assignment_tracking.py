import asyncio
import secrets
import time
import unittest
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select
from backend.db import Session
from backend.models import User, Customer, Restaurant, Driver, Order, Address
from backend.services import delivery_service, tracking_service, assignment_tracking_service, navigation_service
from backend.services.websocket_manager import WebSocketManager, Peer


class AssignmentTrackingTests(unittest.TestCase):
    def setUp(self):
        self.db = Session()
        self.customer = User(name='Assignment audit customer', email='tracking-audit-'+secrets.token_hex(8)+'@example.com', password='x', role='customer')
        self.owner = User(name='Assignment audit store', email='tracking-audit-'+secrets.token_hex(8)+'@example.com', password='x', role='restaurant')
        self.driver = User(name='Assignment audit driver', email='tracking-audit-'+secrets.token_hex(8)+'@example.com', password='x', role='driver', phone='15550000000')
        self.db.add_all([self.customer, self.owner, self.driver]);self.db.flush()
        self.store = Restaurant(id=self.owner.id, name='Assignment audit', address='Audit restaurant', country='US', latitude=36.15, longitude=-86.78, is_open=True)
        self.profile = Driver(id=self.driver.id, online=True, vehicle_type='Car', vehicle_number='AUDIT')
        self.db.add_all([Customer(id=self.customer.id), self.store, self.profile]);self.db.flush()
        self.order = Order(customer_id=self.customer.id, restaurant_id=self.owner.id, request_key=secrets.token_hex(16), mode='delivery', payment_mode='Cash', status='ACCEPTED', address='Audit customer address', total=Decimal(20))
        self.db.add(self.order);self.db.flush()
        self.gps = {'type':'driver_location', 'driver_id':self.driver.id, 'order_id':None, 'latitude':36.14, 'longitude':-86.79, 'heading':30, 'speed':0, 'timestamp':int(time.time()*1000)}

    def tearDown(self):
        self.db.rollback();self.db.close()

    def test_acceptance_immediately_exposes_driver_and_current_gps(self):
        with patch('backend.services.dispatch_service.eligible', return_value={'distance_miles':1}), patch('backend.services.driver_offer_service.validate_accept'):
            delivery_service.accept(self.db, self.driver, self.order.id)
        self.db.flush()
        with patch('backend.services.redis_geo_service.live', return_value=self.gps), patch('backend.services.navigation_service.route', return_value=None):
            result = tracking_service.tracking(self.db, self.customer, self.order.id)
        self.assertEqual(result['driver_status'], 'DRIVER_ASSIGNED')
        self.assertEqual(result['driver']['name'], self.driver.name)
        self.assertEqual(result['driver']['vehicle_number'], 'AUDIT')
        self.assertEqual(result['location']['latitude'], 36.14)

    def test_assignment_snapshot_rebinds_gps_without_fabricating_position(self):
        self.order.driver_id=self.driver.id;self.db.flush()
        with patch('backend.services.assignment_tracking_service.Session') as factory, patch('backend.services.redis_geo_service.live', return_value=self.gps):
            factory.return_value.__enter__.return_value=self.db
            result=assignment_tracking_service.assignment_location(self.order.id,self.driver.id)
        self.assertEqual(result['order_id'],self.order.id)
        self.assertEqual(result['latitude'],self.gps['latitude'])
        self.assertEqual(result['timestamp'],self.gps['timestamp'])
        self.assertEqual(result['driver']['name'],self.driver.name)
        self.assertIsNone(self.gps['order_id'])

    def test_offline_stale_and_other_driver_are_not_broadcast(self):
        self.order.driver_id=self.driver.id;self.db.flush()
        with patch('backend.services.assignment_tracking_service.Session') as factory, patch('backend.services.redis_geo_service.live', return_value={**self.gps,'timestamp':int((time.time()-60)*1000)}):
            factory.return_value.__enter__.return_value=self.db
            self.assertIsNone(assignment_tracking_service.assignment_location(self.order.id,self.driver.id))
            self.assertIsNone(assignment_tracking_service.assignment_location(self.order.id,self.driver.id+999999))
            self.profile.online=False;self.db.flush()
            self.assertIsNone(assignment_tracking_service.assignment_location(self.order.id,self.driver.id))

    def test_driver_details_do_not_require_a_gps_fix(self):
        self.order.driver_id=self.driver.id;self.db.flush()
        with patch('backend.services.redis_geo_service.live', return_value=None), patch('backend.services.navigation_service.route', return_value=None):
            result=tracking_service.tracking(self.db,self.customer,self.order.id)
        self.assertEqual(result['driver']['id'],self.driver.id)
        self.assertIsNone(result['location'])

    def test_fallback_uses_actual_restaurant_and_customer_coordinates(self):
        address=Address(customer_id=self.customer.id,label='Audit',details=self.order.address,country='US',latitude=36.17,longitude=-86.77)
        self.db.add(address);self.db.flush()
        with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY':''}):
            pickup=navigation_service.route(self.order,self.store,self.gps,'DRIVER_ASSIGNED',db=self.db)
            dropoff=navigation_service.route(self.order,self.store,self.gps,'PICKED_UP',db=self.db)
            missing=navigation_service.route(self.order,self.store,None,'DRIVER_ASSIGNED',db=self.db)
        self.assertEqual(pickup['restaurant_location'], {'lat':36.15,'lng':-86.78})
        self.assertEqual(dropoff['customer_location'], {'lat':36.17,'lng':-86.77})
        self.assertTrue(dropoff['estimated'])
        self.assertIsNone(missing)


class AssignmentBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_assignment_pushes_cached_gps_to_owner_immediately(self):
        manager=WebSocketManager()
        owner=Peer(None,'order',40,{'role':'customer','sub':'10'})
        other=Peer(None,'order',40,{'role':'customer','sub':'99'})
        manager.add(owner);manager.add(other)
        event={'type':'order_update','order_id':40,'customer_id':10,'restaurant_id':20,'driver_id':30,'activity_status':'DRIVER_ASSIGNED'}
        fix={**event,'type':'driver_location','latitude':36.14,'longitude':-86.79}
        with patch('backend.services.assignment_tracking_service.assignment_location',return_value=fix), patch('backend.services.gps_auth_service.visible_order',return_value=True):
            await manager.order_update(event)
        self.assertEqual(owner.queue.get_nowait()['type'],'order_update')
        self.assertEqual(owner.queue.get_nowait()['type'],'driver_location')
        self.assertTrue(other.queue.empty())

    async def test_no_driver_does_not_push_fake_gps(self):
        manager=WebSocketManager();owner=Peer(None,'order',40,{'role':'customer','sub':'10'});manager.add(owner)
        with patch('backend.services.assignment_tracking_service.assignment_location') as location:
            await manager.order_update({'order_id':40,'customer_id':10,'driver_id':None,'activity_status':'DRIVER_QUEUED'})
        location.assert_not_called();self.assertEqual(owner.queue.qsize(),1)


if __name__=='__main__':unittest.main()
