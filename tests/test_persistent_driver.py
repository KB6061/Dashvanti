import jwt
from datetime import timedelta
from backend.config import settings
from backend.models import User, Driver, Customer, Restaurant, Order, now
from backend.services.session_service import issue_tokens

def driver_session(client):
    with client.db_factory() as db:
        user=User(email='driver@example.test',password='unused',name='Test',role='driver')
        db.add(user);db.flush()
        db.add(Driver(id=user.id,online=False))
        db.commit()
        return user.id,issue_tokens(user)

def test_persistent_refresh_and_logout(client):
    _,tokens=driver_session(client)
    claims=jwt.decode(tokens['access_token'],settings.jwt_secret,algorithms=['HS256'],audience='dashvanti')
    claims['exp']=now()-timedelta(seconds=1)
    expired=jwt.encode(claims,settings.jwt_secret,algorithm='HS256')
    assert client.get('/api/me',headers={'Authorization':'Bearer '+expired}).status_code==401
    response=client.post('/api/auth/refresh',json={'refresh_token':tokens['refresh_token']})
    assert response.status_code==200
    headers={'Authorization':'Bearer '+response.json()['access_token']}
    assert client.get('/api/me',headers=headers).status_code==200
    assert client.get('/api/me',headers={'Authorization':'Bearer '+tokens['refresh_token']}).status_code==401
    assert client.post('/api/auth/logout',headers=headers).status_code==200
    assert client.post('/api/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==401

def test_presence_is_persisted_and_controls_gps(client):
    driver_id,tokens=driver_session(client)
    headers={'Authorization':'Bearer '+tokens['access_token']}
    assert client.get('/api/driver/presence').status_code in (401,403)
    for mode,online in [('ONLINE',True),('BREAK',False),('HOME',False)]:
        r=client.post('/api/driver/presence',headers=headers,json={'mode':mode})
        assert r.status_code==200
        assert r.json()['online']==online
        assert client.get('/api/driver/presence',headers=headers).json()['mode']==mode
        with client.db_factory() as db:
            assert bool(db.get(Driver,driver_id).online)==online
    assert client.post('/api/driver/location/update',headers=headers,json={'lat':35.1,'lng':-86.1}).status_code==409
    assert client.post('/api/driver/presence',headers=headers,json={'mode':'INVALID'}).status_code==422

def test_break_keeps_active_delivery_tracking(client,monkeypatch):
    from backend.services import arrival_service
    monkeypatch.setattr(arrival_service,'detect',lambda *args:None)
    driver_id,tokens=driver_session(client)
    headers={'Authorization':'Bearer '+tokens['access_token']}
    with client.db_factory() as db:
        customer=User(email='c@example.test',password='unused',name='C',role='customer')
        restaurant=User(email='r@example.test',password='unused',name='R',role='restaurant')
        db.add_all([customer,restaurant]);db.flush()
        db.add_all([Customer(id=customer.id),Restaurant(id=restaurant.id,name='R',cuisine='Test')]);db.flush()
        db.add(Order(customer_id=customer.id,restaurant_id=restaurant.id,driver_id=driver_id,request_key='presence-test-order',status='PICKED_UP',mode='delivery',address='Test',total=10,delivery_fee=2))
        db.commit()
    assert client.post('/api/driver/presence',headers=headers,json={'mode':'HOME'}).status_code==409
    assert client.post('/api/driver/presence',headers=headers,json={'mode':'BREAK'}).status_code==200
    response=client.post('/api/driver/location/update',headers=headers,json={'lat':35.1,'lng':-86.1})
    assert response.status_code==200
    assert response.json()['latitude']==35.1
