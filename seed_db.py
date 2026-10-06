import os
os.environ['DATABASE_URL'] = 'postgresql://Dashvanti:Dashvanti@127.0.0.1:5432/dashvanti'
os.environ['JWT_SECRET'] = 'DashvantiSuperSecretJWTToken2026WithAtLeast32Chars'
from backend.db import engine
from backend.models import Restaurant, MenuItem, User
from sqlalchemy.orm import Session
from decimal import Decimal

with Session(engine) as db:
    r_count = db.query(Restaurant).count()
    print('Existing restaurants count in DB:', r_count)
    if r_count == 0:
        u1 = User(id=10, email='punjab@dashvanti.com', password='hash1', name='Punjab Grill Owner', phone='+91 9876543210', role='restaurant')
        u2 = User(id=11, email='truffles@dashvanti.com', password='hash2', name='Truffles Owner', phone='+91 9876543211', role='restaurant')
        u3 = User(id=12, email='meghana@dashvanti.com', password='hash3', name='Meghana Owner', phone='+91 9876543212', role='restaurant')
        u4 = User(id=13, email='empire@dashvanti.com', password='hash4', name='Empire Owner', phone='+91 9876543213', role='restaurant')
        db.add_all([u1, u2, u3, u4])
        db.commit()

        r1 = Restaurant(id=10, name='Punjab Grill', cuisine='North Indian, Mughlai', address='Indiranagar, Bengaluru', is_open=True, opening='09:00', closing='23:00', delivery_minutes=30)
        r2 = Restaurant(id=11, name='Truffles', cuisine='American, Burgers, Desserts', address='Koramangala, Bengaluru', is_open=True, opening='10:00', closing='23:30', delivery_minutes=25)
        r3 = Restaurant(id=12, name='Meghana Foods', cuisine='Biryani, Andhra, South Indian', address='Jayanagar, Bengaluru', is_open=True, opening='11:00', closing='22:30', delivery_minutes=20)
        r4 = Restaurant(id=13, name='Empire Restaurant', cuisine='North Indian, Kebabs, Biryani', address='MG Road, Bengaluru', is_open=True, opening='11:00', closing='01:00', delivery_minutes=35)
        db.add_all([r1, r2, r3, r4])
        db.commit()

        items = [
            MenuItem(id=1, restaurant_id=10, name='Butter Chicken', description='Rich, creamy tomato gravy with tender chicken pieces', category='Main Course', price=Decimal('380.00'), veg=False, available=True),
            MenuItem(id=2, restaurant_id=10, name='Paneer Tikka Masala', description='Grilled cottage cheese cubes in spiced onion tomato sauce', category='Main Course', price=Decimal('320.00'), veg=True, available=True),
            MenuItem(id=3, restaurant_id=10, name='Garlic Naan', description='Leavened flatbread brushed with garlic butter', category='Breads', price=Decimal('60.00'), veg=True, available=True),
            MenuItem(id=4, restaurant_id=11, name='All American Cheese Burger', description='Juicy patty topped with melted cheddar, lettuce and pickles', category='Burgers', price=Decimal('280.00'), veg=False, available=True),
            MenuItem(id=5, restaurant_id=11, name='Crispy Veg Burger', description='Crispy vegetable patty with spicy mayo and cheese', category='Burgers', price=Decimal('220.00'), veg=True, available=True),
            MenuItem(id=6, restaurant_id=12, name='Meghana Special Chicken Biryani', description='Signature spicy Andhra style chicken biryani served with raita', category='Biryani', price=Decimal('340.00'), veg=False, available=True),
            MenuItem(id=7, restaurant_id=12, name='Paneer Biryani', description='Aromatic basmati rice cooked with marinated paneer and spices', category='Biryani', price=Decimal('290.00'), veg=True, available=True),
            MenuItem(id=8, restaurant_id=13, name='Chicken Shawarma Roll', description='Slow roasted shredded chicken in pita bread with garlic sauce', category='Rolls', price=Decimal('160.00'), veg=False, available=True)
        ]
        db.add_all(items)
        db.commit()
        print('SUCCESSFULLY_SEEDED_POSTGRES_DB')
