from sqlalchemy import select
from backend.models import Restaurant, MenuItem
from test_workflow import setup_order, account

def test_closed_store_blocks_order_and_suggests_open_stores(client):
    customer,restaurant,_,order=setup_order(client)
    other=account(client,'restaurant','alternative')
    with client.db_factory() as db:
        store=db.scalar(select(Restaurant).where(Restaurant.name=='Kitchen'))
        store_id=store.id
        item_id=db.scalar(select(MenuItem.id).where(MenuItem.restaurant_id==store_id))
        alternative=db.scalar(select(Restaurant).where(Restaurant.id!=store_id))
        alternative.is_open=True
        alternative.name='Open alternative'
        db.commit()
    assert client.get(f'/api/menu/{item_id}/order-availability',headers=customer).json()['is_open'] is True
    assert client.put('/api/cart',headers=customer,json={'menu_item_id':item_id,'quantity':1}).status_code==200
    with client.db_factory() as db:
        db.get(Restaurant,store_id).is_open=False;db.commit()
    result=client.get(f'/api/menu/{item_id}/order-availability',headers=customer).json()
    assert result['is_open'] is False
    assert [row['name'] for row in result['alternatives']]==['Open alternative']
    assert client.put('/api/cart',headers=customer,json={'menu_item_id':item_id,'quantity':2}).status_code==409
    assert client.post('/api/orders',headers=customer,json={'mode':'pickup','request_key':'closed-store-order-1234'}).status_code==409
    assert client.put('/api/cart',headers=customer,json={'menu_item_id':item_id,'quantity':0}).status_code==200
