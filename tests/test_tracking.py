from datetime import timedelta
from sqlalchemy import select
from backend.models import DriverLocation, DeliveryStatus, now
from backend.services import eta_service
from test_workflow import setup_order, account

def test_parallel_tracking_and_permissions(client, monkeypatch):
    c,r,d,o = setup_order(client)
    other = account(client,'customer','tracking-stranger')
    oid=o['id']
    monkeypatch.setattr(eta_service,'route',lambda *args:{'distance_meters':100,'distance_miles':0.06,'drive_minutes':1})
    client.put('/api/delivery/availability',headers=d,json={'online':True})
    assert client.post('/api/driver/location/update',headers=d,json={'latitude':36,'longitude':-86,'heading':0}).status_code==200
    assert client.post(f'/api/orders/{oid}/status',headers=r,json={'status':'ACCEPTED'}).status_code==200
    assert client.post(f'/api/delivery/{oid}/accept',headers=d).status_code==200
    response=client.post('/api/driver/location/update',headers=d,json={'lat':36,'lng':-86,'heading':0,'order_id':oid})
    assert response.status_code==200,response.text
    assert response.json()['order_id']==oid
    assert client.post('/api/driver/location/update',headers=d,json={'lat':36,'lng':-86,'driver_id':99999,'order_id':oid}).status_code==403
    assert client.post('/api/driver/location/update',headers=d,json={'lat':36,'lng':-86,'order_id':99999}).status_code==404
    for status in ['ON_THE_WAY_TO_RESTAURANT','ARRIVED_AT_RESTAURANT']:
        response=client.post('/api/driver/status/update',headers=d,json={'order_id':oid,'status':status})
        assert response.status_code==200,response.text
        assert response.json()['driver_status']==status
        assert response.json()['restaurant_status']=='ACCEPTED'
    assert client.post('/api/driver/status/update',headers=d,json={'order_id':oid,'status':'PICKED_UP'}).status_code==409
    for status in ['PREPARING','PACKING','WRAPPING_UP','READY_FOR_PICKUP']:
        response=client.post(f'/api/order/{oid}/restaurant/status',headers=r,json={'status':status})
        assert response.status_code==200,response.text
        assert response.json()['driver_status']=='ARRIVED_AT_RESTAURANT'
        assert client.get(f'/api/order/{oid}/restaurant/status',headers=c).json()['status']==status
    response=client.get(f'/api/order/{oid}/tracking',headers=c)
    assert response.headers['cache-control']=='no-store'
    assert response.json()['location']['heading']==0
    assert response.json()['location']['stale'] is False
    assert client.get(f'/api/order/{oid}/tracking',headers=other).status_code==404
    assert client.post('/api/driver/status/update',headers=c,json={'order_id':oid,'status':'DELIVERED'}).status_code==403
    assert client.post(f'/api/order/{oid}/restaurant/status',headers=d,json={'status':'PACKING'}).status_code==403
    for status in ['PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED']:
        assert client.post('/api/driver/status/update',headers=d,json={'order_id':oid,'status':status}).status_code==200
    assert client.post('/api/driver/status/update',headers=d,json={'order_id':oid,'status':'ON_THE_WAY_TO_RESTAURANT'}).status_code==409
    with client.db_factory() as db:
        location=db.scalar(select(DriverLocation));location.updated_at=now()-timedelta(minutes=2);db.commit()
        saved=set(db.scalars(select(DeliveryStatus.status).where(DeliveryStatus.order_id==oid)))
        assert {'PACKING','WRAPPING_UP','ARRIVED_AT_RESTAURANT','DELIVERED'}<=saved
    assert client.get(f'/api/order/{oid}/tracking',headers=c).json()['location'] is None
    assert client.post('/api/driver/location/update',headers=d,json={'lat':36,'lng':-86,'heading':0,'order_id':oid}).status_code==409

def test_navigation_route_metadata(monkeypatch):
    from types import SimpleNamespace
    from backend.services import navigation_service as nav
    nav._cache.clear()
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY','test')
    requests=[]
    def get(url,params,timeout):
        requests.append(params)
        leg={'duration':{'value':120},'distance':{'value':900},'end_location':{'lat':36.1,'lng':-86.1}}
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':'OK','routes':[{'legs':[leg,leg] if 'waypoints' in params else [leg],'overview_polyline':{'points':'abc'}}]})
    monkeypatch.setattr(nav.httpx,'get',get)
    order=SimpleNamespace(id=123,driver_id=7,mode='delivery',address='Customer')
    restaurant=SimpleNamespace(address='Restaurant')
    gps={'latitude':36,'longitude':-86,'stale':False}
    result=nav.route(order,restaurant,gps,'ON_THE_WAY_TO_RESTAURANT')
    assert result['eta_seconds']==240 and result['distance_meters']==1800
    assert result['restaurant_location']=={'lat':36.1,'lng':-86.1}
    assert nav.route(order,restaurant,gps,'ON_THE_WAY_TO_RESTAURANT')==result
    assert len(requests)==1
    result=nav.route(order,restaurant,gps,'ON_THE_WAY_TO_CUSTOMER')
    assert result['stage']=='customer' and result['eta_seconds']==120
    assert 'waypoints' not in requests[-1]
    assert nav.route(order,restaurant,gps,'DELIVERED') is None
    gps['stale']=True
    assert nav.route(order,restaurant,gps,'ON_THE_WAY_TO_CUSTOMER') is None
    nav._cache.clear()
