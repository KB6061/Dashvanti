import asyncio
import json
import time
import unittest
from uuid import uuid4
import httpx
import websockets
from sqlalchemy import select,func
from backend.db import Session
from backend.config import settings
from backend.models import User,Driver,Order,DeliveryStatus,DriverLocationHistory,DriverLocation
from backend.models_gps import EssentialGPSPoint
from backend.schemas import AdminUserCreate
from backend.services.operations_service import admin_create_user,admin_delete_user
from backend.services import redis_geo_service as geo
from datetime import timedelta
import test_admin_portal as fixtures

class GPSPointTest(unittest.TestCase):
    setUp=fixtures.AdminPortalTest.setUp
    tearDown=fixtures.AdminPortalTest.tearDown

    def test_route_points_require_time_and_distance(self):
        from backend.services.gps_point_service import route_point
        from backend.models import now
        data={'order_id':self.order.id,'driver_id':self.people['driver'],'latitude':19.2088,'longitude':72.9715,'timestamp':int(time.time()*1000),'event_id':uuid4().hex}
        route_point(self.db,data);self.db.flush()
        first=self.db.scalar(select(EssentialGPSPoint).where(EssentialGPSPoint.order_id==self.order.id))
        first.recorded_at=now()-timedelta(seconds=130);self.db.flush()
        route_point(self.db,{**data,'latitude':19.20881,'event_id':uuid4().hex});self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(EssentialGPSPoint.id)).where(EssentialGPSPoint.order_id==self.order.id)),1)
        first.recorded_at=now()-timedelta(seconds=30);self.db.flush()
        route_point(self.db,{**data,'latitude':19.2288,'event_id':uuid4().hex});self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(EssentialGPSPoint.id)).where(EssentialGPSPoint.order_id==self.order.id)),1)
        first.recorded_at=now()-timedelta(seconds=130);self.db.flush()
        route_point(self.db,{**data,'latitude':19.2288,'event_id':uuid4().hex});self.db.flush()
        self.assertEqual(self.db.scalar(select(func.count(EssentialGPSPoint.id)).where(EssentialGPSPoint.order_id==self.order.id)),2)

class GPSStreamingTest(unittest.TestCase):
    def test_live_pipeline_security_milestones_and_expiry(self):
        asyncio.run(self.pipeline())

    async def pipeline(self):
        prefix='gps-stream-audit-'+uuid4().hex[:10];people={};password=uuid4().hex
        try:
            with Session() as db:
                for role in ('customer','driver','restaurant'):
                    result=admin_create_user(db,AdminUserCreate(role=role,email=prefix+'-'+role+'@example.com',name=prefix+' '+role,password=password))
                    people[role]=result['id']
                db.get(Driver,people['driver']).online=True
                order=Order(customer_id=people['customer'],driver_id=people['driver'],restaurant_id=people['restaurant'],request_key=prefix,mode='delivery',status='READY_FOR_PICKUP',address='Jupiter Hospital, Thane, Maharashtra, India',total=0,delivery_fee=0)
                db.add(order);db.flush();oid=order.id;db.add(DeliveryStatus(order_id=oid,status='DRIVER_ASSIGNED'));db.commit()
            async with httpx.AsyncClient(base_url='https://driver.dashvanti.com/api',timeout=20) as api:
                auth={}
                for role in ('driver','customer'):
                    result=await api.post('/auth/login',json={'email':prefix+'-'+role+'@example.com','password':password,'role':role});self.assertEqual(result.status_code,200,result.text)
                    auth[role]={'Authorization':'Bearer '+result.json()['access_token']}
                result=await api.post('/gps/ticket',headers=auth['driver']);self.assertEqual(result.status_code,200,result.text);driver_ticket=result.json()['ticket']
                result=await api.post('/gps/ticket',params={'order_id':oid},headers=auth['customer']);self.assertEqual(result.status_code,200,result.text);customer_ticket=result.json()['ticket']
                denied=await api.post('/gps/ticket',params={'order_id':oid+99999},headers=auth['customer']);self.assertIn(denied.status_code,(403,404))
                result=await api.post('/gps/admin-ticket',headers={'X-Dashvanti-Admin-Secret':settings.admin_secret});self.assertEqual(result.status_code,200,result.text);admin_ticket=result.json()['ticket']
                self.assertEqual((await api.post('/gps/admin-ticket')).status_code,403)
                async with websockets.connect('wss://driver.dashvanti.com/ws/driver/'+str(people['driver']),proxy=None) as driver,websockets.connect('wss://customer.dashvanti.com/ws/customer/'+str(oid),proxy=None) as customer,websockets.connect('wss://admin.dashvanti.com/ws/admin',proxy=None) as admin:
                    for socket,ticket in ((driver,driver_ticket),(customer,customer_ticket),(admin,admin_ticket)):
                        await socket.send(json.dumps({'ticket':ticket}));self.assertEqual(json.loads(await socket.recv())['type'],'ready')
                    async def event(socket,kind,uid=None):
                        while True:
                            data=json.loads(await asyncio.wait_for(socket.recv(),15))
                            if data['type']=='ping':await socket.send(json.dumps({'type':'pong'}));continue
                            if data['type']==kind and (uid is None or data.get('driver_id')==uid):return data
                    before={}
                    with Session() as db:
                        before['history']=db.scalar(select(func.count(DriverLocationHistory.id)))
                        before['locations']=db.scalar(select(func.count(DriverLocation.driver_id)))
                    for index in range(3):
                        if index:await asyncio.sleep(4)
                        sent=time.monotonic()
                        await driver.send(json.dumps({'latitude':19.2088+index*0.00001,'longitude':72.9715,'heading':90,'speed':3,'accuracy':10,'order_id':oid+1000,'driver_id':people['driver']+999}))
                        ack=await event(driver,'ack')
                        c,a=await asyncio.gather(event(customer,'driver_location',people['driver']),event(admin,'driver_location',people['driver']))
                        self.assertEqual(c['order_id'],oid);self.assertEqual(c['event_id'],ack['event_id']);self.assertEqual(a['event_id'],ack['event_id']);self.assertLess(time.monotonic()-sent,5)
                        if index==0:
                            await driver.send(json.dumps({'latitude':19.2088,'longitude':72.9715}))
                            self.assertEqual((await event(driver,'throttled'))['interval_seconds'],4)
                    self.assertIsNotNone(geo.client().geopos('gps:geo:'+str(people['driver']),str(people['driver']))[0])
                    self.assertGreater(geo.client().ttl('gps:driver:'+str(people['driver'])),0)
                    print('PASS WSS -> Redis Geo -> Kafka -> customer/admin push; 4-second throttle; identity isolation',flush=True)
                    with Session() as db:
                        self.assertEqual(db.scalar(select(func.count(DriverLocationHistory.id))),before['history'])
                        self.assertEqual(db.scalar(select(func.count(DriverLocation.driver_id))),before['locations'])
                        self.assertLessEqual(db.scalar(select(func.count(EssentialGPSPoint.id)).where(EssentialGPSPoint.order_id==oid)),1)
                    for status in ('ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT','PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED'):
                        result=await api.post(f'/orders/{oid}/status',headers=auth['driver'],json={'status':status});self.assertEqual(result.status_code,200,result.text)
                    with Session() as db:
                        kinds=set(db.scalars(select(EssentialGPSPoint.kind).where(EssentialGPSPoint.order_id==oid)))
                        self.assertTrue({'PICKUP','DROP_OFF'}.issubset(kinds),kinds)
                        self.assertEqual(db.scalar(select(func.count(DriverLocationHistory.id))),before['history'])
                    self.assertEqual((await api.post('/gps/ticket',params={'order_id':oid},headers=auth['customer'])).status_code,409)
                    print('PASS zero routine PostgreSQL GPS writes; pickup/drop-off persisted; historical tracking denied',flush=True)
                async with websockets.connect('wss://driver.dashvanti.com/ws/driver/'+str(people['driver']+1),proxy=None) as wrong:
                    await wrong.send(json.dumps({'ticket':driver_ticket}))
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):await wrong.recv()
                self.assertEqual((await api.post('/auth/logout',headers=auth['driver'])).status_code,200)
                async with websockets.connect('wss://driver.dashvanti.com/ws/driver/'+str(people['driver']),proxy=None) as revoked:
                    await revoked.send(json.dumps({'ticket':driver_ticket}))
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):await revoked.recv()
                await asyncio.sleep(50)
                self.assertIsNone(geo.live(people['driver']))
                self.assertIsNone(geo.client().geopos('gps:geo:'+str(people['driver']),str(people['driver']))[0])
                self.assertIsNone(geo.client().zscore(geo.GEO,str(people['driver'])))
                print('PASS live GPS and Geo membership expire automatically',flush=True)
        finally:
            with Session() as db:
                for uid in people.values():
                    user=db.get(User,uid)
                    if user:
                        assert user.email.startswith(prefix)
                        if user.role=='driver':geo.remove(uid)
                        admin_delete_user(db,uid)
                db.commit()

if __name__=='__main__':unittest.main()
