import asyncio
import json
import time
import unittest
from contextlib import AsyncExitStack
from uuid import uuid4
import httpx
import websockets
from sqlalchemy import select, func
from backend.config import settings
from backend.db import Session
from backend.models import User, Driver, Restaurant, Order, DeliveryStatus
from backend.models_order_stream import OrderBroadcastEvent
from backend.schemas import AdminUserCreate
from backend.services.operations_service import admin_create_user, admin_delete_user
from backend.services import redis_geo_service as geo
from backend.services.order_broadcast_service import install

install()


class OrderStreamTest(unittest.TestCase):
    def test_committed_updates_reach_all_portals(self):
        asyncio.run(self.pipeline())

    async def pipeline(self):
        prefix='order-stream-audit-'+uuid4().hex[:10]; people={}; password=uuid4().hex; oid=None
        try:
            with Session() as db:
                for role in ('customer','restaurant','driver'):
                    people[role]=admin_create_user(db,AdminUserCreate(role=role,email=prefix+'-'+role+'@example.com',name=prefix+' '+role,password=password))['id']
                db.get(Driver,people['driver']).online=True
                db.get(Restaurant,people['restaurant']).address='Viviana Mall, Thane, Maharashtra, India'
                row=Order(customer_id=people['customer'],restaurant_id=people['restaurant'],driver_id=people['driver'],request_key=prefix,status='PLACED',mode='delivery',address='Jupiter Hospital, Thane, Maharashtra, India',total=0,delivery_fee=0)
                db.add(row);db.flush();oid=row.id
                db.add(DeliveryStatus(order_id=oid,status='DRIVER_ASSIGNED'));db.commit()
            async with httpx.AsyncClient(base_url='https://driver.dashvanti.com/api',timeout=20) as api:
                auth={};tickets={}
                for role in people:
                    response=await api.post('/auth/login',json={'email':prefix+'-'+role+'@example.com','password':password,'role':role});self.assertEqual(response.status_code,200,response.text)
                    auth[role]={'Authorization':'Bearer '+response.json()['access_token']}
                    response=await api.post('/gps/ticket',headers=auth[role],params={'order_id':oid} if role=='customer' else None);self.assertEqual(response.status_code,200,response.text);tickets[role]=response.json()['ticket']
                tickets['admin']=(await api.post('/gps/admin-ticket',headers={'X-Dashvanti-Admin-Secret':settings.admin_secret})).json()['ticket']
                paths={'customer':'/ws/customer/'+str(oid),'restaurant':'/ws/restaurant/'+str(people['restaurant']),'driver':'/ws/driver/'+str(people['driver']),'admin':'/ws/admin/orders'}
                async with AsyncExitStack() as stack:
                    sockets={}
                    for role,path in paths.items():
                        socket=await stack.enter_async_context(websockets.connect('wss://'+role+'.dashvanti.com'+path,proxy=None))
                        await socket.send(json.dumps({'ticket':tickets[role]}));self.assertEqual(json.loads(await socket.recv())['type'],'ready');sockets[role]=socket
                    async def receive(socket,status):
                        while True:
                            data=json.loads(await asyncio.wait_for(socket.recv(),12))
                            if data['type']=='ping':await socket.send(json.dumps({'type':'pong'}))
                            if data['type']=='order_update' and data['order_id']==oid and data['activity_status']==status:return data
                    for role,status in [('restaurant','ACCEPTED'),('restaurant','PREPARING'),('restaurant','PACKING'),('restaurant','READY'),('driver','ON_THE_WAY_TO_RESTAURANT'),('driver','ARRIVED_AT_RESTAURANT'),('driver','PICKED_UP'),('driver','DELIVERING'),('driver','COMPLETED')]:
                        canonical={'READY':'READY_FOR_PICKUP','DELIVERING':'ON_THE_WAY_TO_CUSTOMER','COMPLETED':'DELIVERED'}.get(status,status)
                        started=time.monotonic()
                        response=await api.post('/order/update',headers=auth[role],json={'order_id':oid,'status':status});self.assertEqual(response.status_code,200,response.text)
                        events=await asyncio.gather(*(receive(socket,canonical) for socket in sockets.values()))
                        self.assertLess(time.monotonic()-started,5)
                        self.assertEqual(len({event['event_id'] for event in events}),1)
                        self.assertTrue(all(event['status']==status if status in {'READY','DELIVERING','COMPLETED'} else event['activity_status']==canonical for event in events))
                        with Session() as db:self.assertEqual(db.get(Order,oid).status,response.json()['status'])
                    print('PASS committed restaurant/driver updates pushed to all four portals, including completion',flush=True)
                denied=await api.post('/order/update',headers=auth['customer'],json={'order_id':oid,'status':'PACKING'});self.assertEqual(denied.status_code,403)
                async with websockets.connect('wss://restaurant.dashvanti.com/ws/restaurant/'+str(people['restaurant']+999),proxy=None) as wrong:
                    await wrong.send(json.dumps({'ticket':tickets['restaurant']}))
                    with self.assertRaises(websockets.exceptions.ConnectionClosed):await wrong.recv()
                print('PASS update role and restaurant channel ownership enforced',flush=True)
            with Session() as db:
                count=db.scalar(select(func.count(OrderBroadcastEvent.id)).where(OrderBroadcastEvent.order_id==oid))
                db.get(Order,oid).status='PACKING';db.flush();db.rollback()
            with Session() as db:
                self.assertEqual(db.get(Order,oid).status,'DELIVERED')
                self.assertEqual(db.scalar(select(func.count(OrderBroadcastEvent.id)).where(OrderBroadcastEvent.order_id==oid)),count)
            print('PASS rolled-back status writes produce no broadcast outbox record',flush=True)
            with geo.client().pubsub() as watcher, Session() as db:
                baseline=db.scalar(select(func.max(OrderBroadcastEvent.id))) or 0
                watcher.subscribe('order_updates');watcher.get_message(timeout=1)
                with db.begin_nested():
                    db.get(Order,oid).status='PACKING'
                    db.add(DeliveryStatus(order_id=oid,status='PACKING'));db.flush()
                message=watcher.get_message(ignore_subscribe_messages=True,timeout=0.3)
                if message:self.assertLessEqual(json.loads(message['data'])['event_id'],baseline)
                db.rollback()
            with Session() as db:
                self.assertEqual(db.scalar(select(func.count(OrderBroadcastEvent.id)).where(OrderBroadcastEvent.order_id==oid)),count)
        finally:
            with Session() as db:
                for uid in people.values():
                    user=db.get(User,uid)
                    if user:
                        assert user.email.startswith(prefix)
                        if user.role=='driver':geo.remove(uid)
                        admin_delete_user(db,uid)
                if oid:
                    from sqlalchemy import delete
                    db.execute(delete(OrderBroadcastEvent).where(OrderBroadcastEvent.order_id==oid))
                db.commit()


class NavigationTest(unittest.TestCase):
    def test_provider_route_becomes_navigation_event(self):
        from unittest.mock import patch
        from backend.services.navigation_stream_service import navigate
        from backend.services.navigation_service import encode_polyline
        class Redis:
            def __init__(self):self.values={};self.messages=[]
            async def get(self,key):return self.values.get(key)
            async def set(self,key,value,**kwargs):self.values[key]=value;return True
            async def delete(self,key):self.values.pop(key,None)
            async def publish(self,channel,value):self.messages.append(json.loads(value))
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'status':'OK','routes':[{'overview_polyline':{'points':encode_polyline([(19,72),(19.001,72)])},'legs':[{'distance':{'value':111},'duration':{'value':60},'steps':[{'distance':{'value':111},'html_instructions':'Head <b>north</b> on <b>Test Street</b>'}]}]}]}
        class Client:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def get(self,*args,**kwargs):return Response()
        redis=Redis()
        with patch('backend.services.navigation_stream_service.destination',return_value=('Test Street','restaurant')),patch('backend.services.navigation_stream_service.httpx.AsyncClient',Client),patch.dict('os.environ',{'GOOGLE_MAPS_SERVER_API_KEY':'test-only-key'}):
            asyncio.run(navigate(redis,{'driver_id':1,'order_id':1,'latitude':19.0005,'longitude':72,'heading':0,'timestamp':int(time.time()*1000)}))
        self.assertEqual(len(redis.messages),1)
        event=redis.messages[0]
        self.assertEqual(event['type'],'navigation');self.assertEqual(event['street'],'Test Street')
        self.assertAlmostEqual(event['distance_meters'],56,delta=1)
        self.assertAlmostEqual(event['eta_seconds'],30,delta=1)
        self.assertIn('north',event['instruction']);self.assertTrue(event['polyline'])

    def test_geometry_and_instructions(self):
        from backend.services.navigation_stream_service import decode_polyline, projection, instruction
        path=decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@')
        self.assertAlmostEqual(path[0][0],38.5)
        self.assertAlmostEqual(path[-1][1],-126.453)
        gap,progress,total=projection([(19,72),(19.001,72)],19.0005,72)
        self.assertLess(gap,1);self.assertAlmostEqual(progress/total,0.5,places=2)
        self.assertEqual(instruction({'html_instructions':'Turn <b>left</b> &amp; continue'}),'Turn  left  & continue')

if __name__=='__main__':unittest.main()
