from sqlalchemy import select, func
from fastapi import HTTPException
from backend.models import Order, Notification, DeliveryStatus
from backend.services import arrival_service, eta_service
from test_workflow import setup_order

def test_arrival_once_at_address(client, monkeypatch):
    _,_,_,data=setup_order(client)
    with client.db_factory() as db:
        order=db.get(Order,data['id'])
        order.status='ON_THE_WAY_TO_CUSTOMER'
        monkeypatch.setattr(eta_service,'route',lambda *a:{'distance_meters':51})
        assert not arrival_service.detect(db,order,36,-86)
        monkeypatch.setattr(eta_service,'route',lambda *a:{'distance_meters':50})
        order.status='PREPARING'
        assert not arrival_service.detect(db,order,36,-86)
        order.status='ON_THE_WAY_TO_CUSTOMER'
        assert arrival_service.detect(db,order,36,-86)
        db.commit()
    with client.db_factory() as db:
        order=db.get(Order,data['id'])
        assert not arrival_service.detect(db,order,36,-86)
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind=='driver-arrived'))==1
        assert db.scalar(select(func.count()).select_from(DeliveryStatus).where(DeliveryStatus.status=='ARRIVED_AT_CUSTOMER'))==1
        order.status='DELIVERED'
        assert not arrival_service.detect(db,order,36,-86)

def test_route_failure_does_not_report_arrival(client, monkeypatch):
    _,_,_,data=setup_order(client)
    def unavailable(*args):
        raise HTTPException(503,'Unavailable')
    monkeypatch.setattr(eta_service,'route',unavailable)
    with client.db_factory() as db:
        order=db.get(Order,data['id']);order.status='ON_THE_WAY_TO_CUSTOMER'
        assert not arrival_service.detect(db,order,36,-86)
