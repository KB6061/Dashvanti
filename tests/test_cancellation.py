from decimal import Decimal
from sqlalchemy import select,func
from backend.models import Order, SystemConfig, User
from backend.services import cancellation_service as service, eta_service
from backend.schemas import CancellationInput
from test_workflow import setup_order, account

def payload(quote):
    return {'reason':'Plans changed','expected_status':quote['status'],'expected_refund':quote['refund'],'expected_charge':quote['charge']}

def test_customer_free_cancel_idempotent(client):
    c,r,d,o=setup_order(client);url=f"/api/orders/{o['id']}/cancellation"
    q=client.get(url,headers=c).json()
    assert q['charge']=='0.00' and q['refund']=='271.00'
    response=client.post(url,headers=c,json=payload(q));assert response.status_code==200,response.text
    assert response.json()['refund_status']=='PENDING'
    assert client.post(url,headers=c,json=payload(q)).json()==response.json()
    with client.db_factory() as db:
        assert db.get(Order,o['id']).status=='CANCELLED'
        assert db.scalar(select(func.count()).select_from(SystemConfig).where(SystemConfig.key==f"refund:cancellation:{o['id']}"))==1

def test_snapshot_and_stale_confirmation(client):
    c,r,d,o=setup_order(client);url=f"/api/orders/{o['id']}/cancellation"
    early=client.get(url,headers=c).json()
    with client.db_factory() as db:
        service.save_policy(db,{'preparation_percent':0,'review_threshold':3});db.commit()
    for status in ['ACCEPTED','PREPARING']:
        assert client.post(f"/api/orders/{o['id']}/status",headers=r,json={'status':status}).status_code==200
    assert client.post(url,headers=c,json=payload(early)).status_code==409
    q=client.get(url,headers=c).json()
    assert q['charge']=='241.00' and q['refund']=='30.00'
    assert client.get(url,headers=r).json()['refund']=='271.00'
    assert client.post(url,headers=c,json=payload(q)).status_code==200
    stranger=account(client,'customer','outsider')
    assert client.get(url,headers=stranger).status_code==404

def test_driver_release_and_after_pickup_review(client,monkeypatch):
    c,r,d,o=setup_order(client);oid=o['id']
    monkeypatch.setattr(eta_service,'route',lambda *args:{'distance_meters':100,'distance_miles':0.06,'drive_minutes':1})
    client.put('/api/delivery/availability',headers=d,json={'online':True})
    client.post('/api/driver/location/update',headers=d,json={'latitude':36,'longitude':-86})
    client.post(f'/api/orders/{oid}/status',headers=r,json={'status':'ACCEPTED'})
    assert client.post(f'/api/delivery/{oid}/accept',headers=d).status_code==200
    url=f'/api/orders/{oid}/cancellation';q=client.get(url,headers=d).json()
    assert q['action']=='release'
    assert client.post(url,headers=d,json=payload(q)).status_code==200
    assert client.get('/api/delivery/available',headers=d).json()==[]
    assert client.post(f'/api/delivery/{oid}/accept',headers=d).status_code==409
    with client.db_factory() as db:
        order=db.get(Order,oid);assert order.driver_id is None and order.status=='ACCEPTED'
        order.status='PICKED_UP';db.commit()
    assert client.get(url,headers=c).status_code==409
    with client.db_factory() as db:
        order=db.get(Order,oid);q=service.quote(db,order,'admin')
        result=service.cancel(db,None,oid,CancellationInput(**payload(q)),admin=True)
        assert result['refund']=='271.00';db.commit()

def test_previous_refund_caps_retained_charge(client):
    import json
    c,r,d,o=setup_order(client)
    with client.db_factory() as db:
        db.get(Order,o['id']).status='PREPARING'
        db.add(SystemConfig(key='refund:test',value=json.dumps({'order_id':o['id'],'amount':'270','status':'PENDING'})))
        db.commit()
    response=client.get(f"/api/orders/{o['id']}/cancellation",headers=c)
    assert response.status_code==200,response.text
    assert response.json()['charge']=='1.00'
    assert response.json()['refund']=='0.00'
