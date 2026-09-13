
from test_workflow import account
from backend.models import User
from sqlalchemy import select

def test_sound_preference_persisted_per_user(client):
    users = [account(client, role) for role in ['customer','restaurant','driver']]
    for headers in users:
        assert client.get('/api/me/order-sound', headers=headers).json()['enabled'] is False
        assert client.put('/api/me/order-sound', headers=headers,json={'enabled':True}).status_code==200
        assert client.get('/api/me/order-sound',headers=headers).json()['enabled'] is True
    with client.db_factory() as db:
        assert all(row.order_sound_enabled for row in db.scalars(select(User)))
    assert client.put('/api/me/order-sound',headers=users[0],json={'enabled':False}).status_code==200
    assert client.get('/api/me/order-sound',headers=users[0]).json()['enabled'] is False
    assert client.get('/api/me/order-sound',headers=users[1]).json()['enabled'] is True
    assert client.get('/api/me/order-sound').status_code in (401,403)
