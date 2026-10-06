import os
os.environ['DATABASE_URL'] = 'postgresql://Dashvanti:Dashvanti@127.0.0.1:5432/dashvanti'
os.environ['JWT_SECRET'] = 'DashvantiSuperSecretJWTToken2026WithAtLeast32Chars'
from backend.db import engine
from backend.models import User, Customer, Driver, Restaurant, MenuItem
from sqlalchemy.orm import Session
import hashlib

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

with Session(engine) as db:
    # Ensure Test Users exist
    users = [
        User(id=1, email='customer@dashvanti.com', password=hash_pw('password123'), name='Rahul Sharma', phone='+91 9876543210', role='customer'),
        User(id=2, email='owner_punjab@dashvanti.com', password=hash_pw('password123'), name='Punjab Grill Manager', phone='+91 9876543211', role='restaurant'),
        User(id=3, email='owner_truffles@dashvanti.com', password=hash_pw('password123'), name='Truffles Manager', phone='+91 9876543212', role='restaurant'),
        User(id=4, email='driver_rajesh@dashvanti.com', password=hash_pw('password123'), name='Rajesh Kumar', phone='+91 9876543213', role='driver'),
        User(id=5, email='driver_amit@dashvanti.com', password=hash_pw('password123'), name='Amit Verma', phone='+91 9876543214', role='driver'),
    ]

    for u in users:
        existing = db.get(User, u.id)
        if not existing:
            db.add(u)
    db.commit()

    # Ensure Customer profile
    if not db.get(Customer, 1):
        db.add(Customer(id=1, order_mode='delivery'))

    # Ensure Driver profiles
    if not db.get(Driver, 4):
        db.add(Driver(id=4, vehicle_type='Hero Splendor', vehicle_number='KA 03 EV 4821', online=True))
    if not db.get(Driver, 5):
        db.add(Driver(id=5, vehicle_type='TVS Apache', vehicle_number='KA 05 EX 9988', online=True))

    db.commit()
    print('ROLE_ACCOUNTS_SEEDED_SUCCESSFULLY')
