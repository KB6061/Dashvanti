from sqlalchemy import select
from backend.models import Outbox, PasswordReset, Order, Restaurant

def account(client, role, name=None):
    data = {'email':f'{name or role}@example.com','name':name or role,'password':'Strong-password-123','role':role}
    assert client.post('/api/auth/register',json=data).status_code == 201
    result = client.post('/api/auth/login',json={k:v for k,v in data.items() if k!='name'})
    assert result.status_code == 200
    return {'Authorization':'Bearer '+result.json()['access_token']}

def setup_order(client, mode='delivery', tip='0'):
    from backend.schemas import FundRuleInput
    from backend.services.fund_service import save_rule
    with client.db_factory() as db:
        save_rule(db, 'delivery_fee', FundRuleInput(value='30'))
        db.commit()
    c,r,d = [account(client,role) for role in ['customer','restaurant','driver']]
    profile = {'name':'Kitchen','cuisine':'Indian','address':'12 Main Street','is_open':True,'opening':'09:00','closing':'22:00','delivery_minutes':30}
    assert client.put('/api/restaurant/profile',headers=r,json=profile).status_code == 200
    item = client.post('/api/menu',headers=r,json={'name':'Bowl','price':'120.50'}).json()
    cart_response = client.put('/api/cart',headers=c,json={'menu_item_id':item['id'],'quantity':2})
    assert cart_response.status_code == 200
    cart_data = cart_response.json()
    assert cart_data['groups'][0]['restaurant_name'] == 'Kitchen'
    assert cart_data['groups'][0]['restaurant_address'] == '12 Main Street'
    assert cart_data['groups'][0]['item_count'] == 2
    quote = client.post('/api/cart/quote',headers=c,json={'mode':mode, 'tip':tip})
    assert quote.status_code == 200
    assert quote.json()['groups'][0]['restaurant_name'] == 'Kitchen'
    assert float(quote.json()['total']) == (271+float(tip) if mode=='delivery' else 241)
    address = client.post('/api/addresses',headers=c,json={'label':'Home','details':'123 Home Street'}).json()
    data = {'tip':tip,'mode':mode,'address_id':address['id'],'request_key':'unique-order-key-12345'}
    response = client.post('/api/orders',headers=c,json=data)
    assert response.status_code == 201, response.text
    order = response.json()
    assert client.post('/api/orders',headers=c,json=data).json()['id'] == order['id']
    assert float(order['total']) == (271+float(tip) if mode=='delivery' else 241)
    with client.db_factory() as db:
        stored_order = db.get(Order, order['id'])
        restaurant_id = db.scalar(select(Restaurant.id).where(Restaurant.name == 'Kitchen'))
        assert stored_order.restaurant_id == restaurant_id
        assert stored_order.mode == mode
        assert stored_order.address == ('123 Home Street' if mode == 'delivery' else 'Pickup at restaurant')
    return c,r,d,order

def test_delivery_and_authorization(client, monkeypatch):
    from backend.services import eta_service
    monkeypatch.setattr(eta_service,"route",lambda *args: {"distance_meters":100,"distance_miles":0.06,"drive_minutes":1})
    c,r,d,o = setup_order(client)
    oid = o['id']
    stranger = account(client,'customer','stranger')
    assert client.get(f'/api/orders/{oid}',headers=stranger).status_code == 404
    assert client.post(f'/api/orders/{oid}/status',headers=c,json={'status':'DELIVERED'}).status_code == 403
    assert client.post(f'/api/orders/{oid}/status',headers=r,json={'status':'DELIVERED'}).status_code == 409
    for status in ['CONFIRMED','PREPARING','READY_FOR_PICKUP']:
        assert client.post(f'/api/orders/{oid}/status',headers=r,json={'status':status}).status_code == 200
    assert client.post(f'/api/delivery/{oid}/accept',headers=d).status_code == 409
    client.put('/api/delivery/availability',headers=d,json={'online':True})
    client.post('/api/driver/location/update',headers=d,json={'latitude':36,'longitude':-86})
    assert client.post(f'/api/delivery/{oid}/accept',headers=d).status_code == 200
    other = account(client,'driver','other-driver')
    client.put('/api/delivery/availability',headers=other,json={'online':True})
    assert client.post(f'/api/delivery/{oid}/accept',headers=other).status_code == 409
    for status in ['ON_THE_WAY_TO_RESTAURANT','PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED']:
        assert client.post(f'/api/orders/{oid}/status',headers=d,json={'status':status}).status_code == 200
    assert float(client.get('/api/stats',headers=d).json()['revenue']) == 30
    assert client.post(f'/api/orders/{oid}/review',headers=c,json={'restaurant':5,'driver':4,'text':'Great meal'}).status_code == 201
    assert client.post(f'/api/orders/{oid}/review',headers=c,json={'restaurant':5,'text':'Duplicate'}).status_code == 409
    assert client.post(f'/api/orders/{oid}/reorder',headers=c).status_code == 200
    with client.db_factory() as db:
        events = set(db.scalars(select(Outbox.event_type)))
        assert {'ORDER_CREATED','ORDER_CONFIRMED','DELIVERY_ASSIGNED','ORDER_PICKED_UP','ORDER_DELIVERED'} <= events

def test_pickup(client):
    c,r,d,o = setup_order(client,'pickup')
    for status in ['CONFIRMED','PREPARING','READY_FOR_PICKUP','DELIVERED']:
        assert client.post(f"/api/orders/{o['id']}/status",headers=r,json={'status':status}).status_code == 200

def test_password_reset_revokes_sessions(client):
    import json
    user = account(client,'customer')
    assert client.post('/api/auth/forgot',json={'email':'customer@example.com'}).status_code == 200
    with client.db_factory() as db:
        mail = db.scalar(select(Outbox).where(Outbox.event_type=='MAIL_PASSWORD_RESET'))
        token = json.loads(mail.payload)['url'].split('token=')[1]
    data = {'token':token,'password':'Another-strong-password'}
    assert client.post('/api/auth/reset',json=data).status_code == 200
    assert client.get('/api/me',headers=user).status_code == 401
    assert client.post('/api/auth/reset',json=data).status_code == 400

def test_upload_access(client):
    import io
    from PIL import Image
    c = account(client,'customer')
    other = account(client,'customer','another')
    stream = io.BytesIO()
    Image.new('RGB',(10,10)).save(stream,format='PNG')
    response = client.post('/api/files',headers=c,data={'purpose':'profile'},files={'file':('../../evil.png',stream.getvalue(),'image/png')})
    assert response.status_code == 201, response.text
    file_id = response.json()['id']
    assert client.get(f'/api/files/{file_id}',headers=other).status_code == 404
    assert client.get(f'/api/files/{file_id}',headers=c).status_code == 200
    assert client.post('/api/files',headers=c,data={'purpose':'profile'},files={'file':('bad.png',b'not an image','image/png')}).status_code == 400

def test_tip_saved_and_eta_owned_address(client, monkeypatch):
    from decimal import Decimal
    from backend.services import eta_service
    from backend.services.order_service import allocate_tip
    from backend.models import Address
    c,r,d,order = setup_order(client, tip='2.51')
    with client.db_factory() as db:
        assert db.get(Order, order['id']).tip == Decimal('2.51')
    assert sum(allocate_tip(Decimal('2.51'), [1,2,3]).values()) == Decimal('2.51')
    assert client.post(f"/api/orders/{order['id']}/reorder", headers=c).status_code == 200
    addresses = client.get('/api/addresses', headers=c).json()
    seen=[]
    def route(origin,destination):
        seen.append((origin,destination))
        return {'drive_minutes':12,'distance_miles':4.2}
    monkeypatch.setattr(eta_service,'route',route)
    eta=client.get('/api/cart/eta',headers=c,params={'address_id':addresses[0]['id']})
    assert eta.status_code == 200, eta.text
    assert eta.json()['minutes']==42
    assert seen==[('12 Main Street','123 Home Street')]
    assert client.get('/api/cart/eta',headers=c,params={'address_id':999999}).status_code==400
    assert client.post('/api/cart/quote',headers=c,json={'mode':'delivery','tip':'-1'}).status_code==422
    assert client.post('/api/cart/quote',headers=c,json={'mode':'pickup','tip':'2'}).json()['tip']==0

def test_pdf_reports_and_access(client, monkeypatch):
    from backend.services import report_service
    from backend.models import User
    c, r, d, order = setup_order(client, tip='2.50')
    path = f"/api/reports/orders/{order['id']}/bill"
    for headers in (c, r):
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.content.startswith(b'%PDF-')
        assert 'attachment' in response.headers['content-disposition']
    stranger = account(client, 'customer', 'pdf-stranger')
    assert client.get(path, headers=stranger).status_code == 404
    assert client.get(path, headers=d).status_code == 403
    assert client.get('/api/reports/earnings', headers=c).status_code == 403
    assert client.get('/api/reports/earnings?period=invalid', headers=d).status_code == 400
    assert client.get('/api/reports/earnings', headers=d).content.startswith(b'%PDF-')
    with client.db_factory() as db:
        driver = db.scalar(select(User).where(User.role == 'driver'))
        stored = db.get(Order, order['id'])
        stored.driver_id = driver.id
        stored.status = 'DELIVERED'
        db.commit()
        captured = {}
        def capture(title, notes, rows):
            captured['rows'] = rows
            return b'%PDF-test'
        monkeypatch.setattr(report_service, 'pdf', capture)
        report_service.earnings(db, driver, 'monthly')
        assert captured['rows'][-1][-1] == '$32.50'
        stored.status = 'PLACED'
        db.commit()
        report_service.earnings(db, driver, 'monthly')
        assert captured['rows'][-1][-1] == '$0.00'

def test_saved_address_defaults(client):
    from backend.models import Address
    customer = account(client, 'customer', 'address-owner')
    other = account(client, 'customer', 'address-other')
    first = client.post('/api/addresses', headers=customer, json={'label':'Home', 'details':'123 Main Street', 'place_id':'place-home', 'is_default':True}).json()
    second = client.post('/api/addresses', headers=customer, json={'label':'Work', 'details':'456 Work Street', 'is_default':False}).json()
    assert client.get('/api/addresses', headers=customer).json()[0]['id'] == first['id']
    data = {'label':'Work', 'details':'456 Work Street', 'place_id':'place-work', 'is_default':True}
    assert client.put(f"/api/addresses/{second['id']}", headers=customer, json=data).status_code == 200
    assert client.put(f"/api/addresses/{second['id']}", headers=other, json=data).status_code == 404
    rows = client.get('/api/addresses', headers=customer).json()
    assert rows[0]['id'] == second['id']
    assert sum(row['is_default'] for row in rows) == 1
    with client.db_factory() as db:
        assert db.get(Address, second['id']).place_id == 'place-work'
        assert not db.get(Address, first['id']).is_default
    data['is_default'] = False
    client.put(f"/api/addresses/{second['id']}", headers=customer, json=data)
    assert not any(row['is_default'] for row in client.get('/api/addresses', headers=customer).json())
    assert len(client.get('/api/addresses', headers=customer).json()) == 2

def test_pdf_local_delivery_time(client, monkeypatch):
    from datetime import datetime
    from backend.models import DeliveryStatus, User
    from backend.services import report_service
    assert report_service.local_time(datetime(2026,9,11,18,5), 'America/Chicago') == 'Sep 11, 2026 01:05 PM CDT'
    assert report_service.local_time(datetime(2026,1,11,18,5), 'America/Chicago') == 'Jan 11, 2026 12:05 PM CST'
    c, r, d, order = setup_order(client)
    captured = {}
    def capture(title, notes, rows):
        captured['notes'] = notes
        return b'%PDF-test'
    monkeypatch.setattr(report_service, 'pdf', capture)
    with client.db_factory() as db:
        stored = db.get(Order, order['id'])
        customer = db.get(User, stored.customer_id)
        report_service.bill(db, customer, stored.id)
        assert 'Delivery date and time: Not delivered yet' in captured['notes']
        stored.status = 'DELIVERED'
        db.add(DeliveryStatus(order_id=stored.id, status='DELIVERED', created_at=datetime(2026,9,11,18,5)))
        db.commit()
        report_service.bill(db, customer, stored.id, 'America/Chicago')
        assert 'Delivery date and time: Sep 11, 2026 01:05 PM CDT' in captured['notes']

def test_menu_instructions_persist(client):
    c, r, d, original = setup_order(client)
    cart = client.post(f"/api/orders/{original['id']}/reorder", headers=c).json()
    item_id = cart['items'][0]['menu_item_id']
    note = 'Spice: Mild; No cutlery; Sauce on the side'
    result = client.put('/api/cart', headers=c, json={'menu_item_id':item_id, 'quantity':2, 'special_instructions':note})
    assert result.status_code == 200
    assert result.json()['items'][0]['special_instructions'] == note
    client.put('/api/cart', headers=c, json={'menu_item_id':item_id, 'quantity':3})
    assert client.get('/api/cart', headers=c).json()['items'][0]['special_instructions'] == note
    address = client.get('/api/addresses', headers=c).json()[0]['id']
    placed = client.post('/api/orders', headers=c, json={'mode':'delivery','address_id':address,'request_key':'menu-preferences-test-12345'})
    assert placed.status_code == 201
    data = client.get(f"/api/orders/{placed.json()['id']}", headers=r).json()
    assert data['items'][0]['special_instructions'] == note
    assert client.put('/api/cart', headers=c, json={'menu_item_id':item_id,'quantity':1,'special_instructions':'x'*1001}).status_code == 422

def test_select_address_atomic(client):
    from backend.models import Address
    c=account(client,'customer','address-popup')
    data={'label':'Home','details':'123 Test Street','latitude':36.1,'longitude':-86.8,'is_default':True}
    response=client.post('/api/addresses/select',headers=c,json=data)
    assert response.status_code==200, response.text
    address_id=response.json()['id']
    assert client.get('/api/customer/location',headers=c).json()['address']=='123 Test Street'
    assert client.get('/api/addresses',headers=c).json()[0]['is_default']
    data.update(id=address_id,details='456 Updated Street',is_default=False)
    assert client.post('/api/addresses/select',headers=c,json=data).status_code==200
    assert len(client.get('/api/addresses',headers=c).json())==1
    other=account(client,'customer','other-popup')
    assert client.post('/api/addresses/select',headers=other,json=data).status_code==404
    data['latitude']=100
    assert client.post('/api/addresses/select',headers=c,json=data).status_code==422
