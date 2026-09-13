
from datetime import timedelta
from sqlalchemy import select
from backend.models import User, DriverLocation, Order, Notification, now
from backend.services import dispatch_service, eta_service
from fastapi import HTTPException
from test_workflow import account, setup_order
import pytest

def test_nearby_accept_and_admin_reassignment(client, monkeypatch):
    customer, restaurant, driver, order = setup_order(client)
    second = account(client, 'driver', 'second')
    far = account(client, 'driver', 'far')
    for headers, latitude in [(driver,36),(second,37),(far,38)]:
        client.put('/api/delivery/availability',headers=headers,json={'online':True})
        response=client.post('/api/driver/location/update',headers=headers,json={'latitude':latitude,'longitude':-86})
        assert response.status_code==200,response.text
    monkeypatch.setattr(eta_service,'route',lambda origin,destination:{'distance_meters':5000 if origin[0]==38 else 4828.032,'distance_miles':3,'drive_minutes':5})
    oid=order['id']
    assert client.post(f'/api/orders/{oid}/status',headers=restaurant,json={'status':'ACCEPTED'}).status_code==200
    assert len(client.get('/api/delivery/available',headers=driver).json())==1
    assert client.get('/api/delivery/available',headers=far).json()==[]
    assert client.post(f'/api/delivery/{oid}/accept',headers=far).status_code==409
    assert client.post(f'/api/delivery/{oid}/accept',headers=driver).status_code==200
    assert client.post(f'/api/delivery/{oid}/accept',headers=second).status_code==409
    with client.db_factory() as db:
        first_id=db.scalar(select(User.id).where(User.email=='driver@example.com'))
        second_id=db.scalar(select(User.id).where(User.email=='second@example.com'))
        assert db.scalar(select(Notification.id).where(Notification.user_id==second_id,Notification.kind=='delivery-claimed'))
        result=dispatch_service.reassign(db,oid,second_id,first_id,'Pickup delayed')
        db.commit()
        assert result['driver_id']==second_id
    with client.db_factory() as db:
        assert db.get(Order,oid).driver_id==second_id
        assert db.scalar(select(Notification.id).where(Notification.user_id==first_id,Notification.kind=='delivery-reassigned'))
        with pytest.raises(HTTPException):
            dispatch_service.reassign(db,oid,first_id,first_id,'Stale assignment')
        db.get(Order,oid).status='PICKED_UP';db.commit()
        with pytest.raises(HTTPException):
            dispatch_service.reassign(db,oid,first_id,second_id,'Too late')
    assert client.get(f'/api/orders/{oid}',headers=driver).status_code==404
    assert client.get(f'/api/operations/orders/{oid}/nearby-drivers',headers=customer).status_code==403

def test_driver_requires_fresh_gps(client, monkeypatch):
    customer,restaurant,driver,order=setup_order(client)
    client.put('/api/delivery/availability',headers=driver,json={'online':True})
    monkeypatch.setattr(eta_service,'route',lambda *args:{'distance_meters':100,'distance_miles':0.06,'drive_minutes':1})
    client.post(f"/api/orders/{order['id']}/status",headers=restaurant,json={'status':'ACCEPTED'})
    assert client.get('/api/delivery/available',headers=driver).json()==[]
    client.post('/api/driver/location/update',headers=driver,json={'latitude':36,'longitude':-86})
    with client.db_factory() as db:
        location=db.scalar(select(DriverLocation));location.updated_at=now()-timedelta(minutes=3);db.commit()
    assert client.post(f"/api/delivery/{order['id']}/accept",headers=driver).status_code==409
