import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import select
from backend.models import User,CustomerLocation,Address,DeliveryStatus,Order
from backend.services.auth_service import passwords
import test_admin_portal as fixtures

class SignupLocationActionsTest(unittest.TestCase):
    setUp=fixtures.AdminPortalTest.setUp
    tearDown=fixtures.AdminPortalTest.tearDown

    def login(self,role):
        user=self.db.get(User,self.people[role]);user.password=passwords.hash('ActionsTest1');self.db.commit()
        with patch('backend.services.auth_service.emit'):
            data=self.client.post('/api/auth/login',json={'email':user.email,'password':'ActionsTest1','role':role}).json()
        return {'Authorization':'Bearer '+data['access_token']}

    def test_signup_stores_exact_gps_default_address_and_allows_office_change(self):
        email=uuid4().hex+'@example.com'
        found={'country':'US','latitude':36.0569,'longitude':-86.7454,'address':'Verified nearby address, Nashville, TN, USA'}
        with patch('backend.services.restaurant_location_service.geocode',return_value=found),patch('backend.services.auth_service.emit'):
            response=self.client.post('/api/auth/register',json={'email':email,'name':'GPS Signup','password':'ActionsTest1','role':'customer','latitude':36.056898,'longitude':-86.7453775})
        self.assertEqual(response.status_code,201,response.text)
        uid=response.json()['id'];row=self.db.get(CustomerLocation,uid)
        self.assertEqual((row.latitude,row.longitude),(36.056898,-86.7453775))
        self.assertEqual(row.country,'US');self.assertTrue(row.address.startswith('Near '))
        address=self.db.scalar(select(Address).where(Address.customer_id==uid));self.assertEqual(address.label,'Current location');self.assertTrue(address.is_default)
        with patch('backend.services.auth_service.emit'):
            token=self.client.post('/api/auth/login',json={'email':email,'password':'ActionsTest1','role':'customer'}).json()['access_token']
        response=self.client.post('/api/addresses/select',headers={'Authorization':'Bearer '+token},json={'id':address.id,'label':'Office','details':'Office, Nashville, TN, USA','is_default':True,'latitude':36.08,'longitude':-86.73,'country':'US'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.db.get(CustomerLocation,uid).latitude,36.08);self.assertEqual(self.db.get(Address,address.id).label,'Office')

    def test_signup_without_permission_and_invalid_coordinates(self):
        payload={'email':uuid4().hex+'@example.com','name':'No GPS','password':'ActionsTest1','role':'customer'}
        with patch('backend.services.auth_service.emit'):
            response=self.client.post('/api/auth/register',json=payload)
        self.assertEqual(response.status_code,201,response.text);self.assertIsNone(self.db.get(CustomerLocation,response.json()['id']))
        for coordinates in ({'latitude':91,'longitude':0},{'latitude':0}):
            response=self.client.post('/api/auth/register',json={**payload,'email':uuid4().hex+'@example.com',**coordinates})
            self.assertEqual(response.status_code,422)

    def test_restaurant_driver_and_admin_transitions_persist_database_history(self):
        restaurant=self.login('restaurant');driver=self.login('driver')
        self.order.status='PLACED';self.order.mode='pickup';self.db.commit()
        for status in ['ACCEPTED','PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP','DELIVERED']:
            with patch('backend.services.delivery_service.emit'):
                response=self.client.post(f'/api/orders/{self.order.id}/status',headers=restaurant,json={'status':status})
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(self.order.status,status)
            self.assertTrue(self.db.scalar(select(DeliveryStatus.id).where(DeliveryStatus.order_id==self.order.id,DeliveryStatus.status==status)))
        self.order=Order(customer_id=self.people['customer'],restaurant_id=self.people['restaurant'],driver_id=self.people['driver'],request_key=uuid4().hex,mode='delivery',address='Test',status='READY_FOR_PICKUP',total=25,delivery_fee=3)
        self.db.add(self.order);self.db.flush();self.db.add(DeliveryStatus(order_id=self.order.id,status='READY_FOR_PICKUP'));self.db.add(DeliveryStatus(order_id=self.order.id,status='DRIVER_ASSIGNED'));self.db.commit()
        for status in ['ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT','PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED']:
            with patch('backend.services.delivery_service.emit'):
                response=self.client.post(f'/api/orders/{self.order.id}/status',headers=driver,json={'status':status})
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(self.db.scalar(select(DeliveryStatus.id).where(DeliveryStatus.order_id==self.order.id,DeliveryStatus.status==status)))

if __name__=='__main__':unittest.main()
