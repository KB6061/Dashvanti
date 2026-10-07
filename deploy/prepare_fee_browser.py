import os,sys,json,secrets
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
from sqlalchemy import select
from backend.db import Session
from backend.models import User,Customer,CustomerLocation,Restaurant,Address,MenuItem,CartItem
from backend.delivery_fee_models import Country
from backend.config import settings as cfg
from datetime import datetime,timezone,timedelta
import jwt
Store=import_module(settings.SESSION_ENGINE).SessionStore
admin=Store();admin['admin_authenticated']=True;admin.create()
data={'admin_session':admin.session_key,'admin_cookie_name':settings.SESSION_COOKIE_NAME}
with Session() as db:
 if db.scalar(select(Country.id).where(Country.country_code=='ZZ')):raise RuntimeError('Audit country already exists')
 pair=db.execute(select(Restaurant,MenuItem).join(MenuItem,MenuItem.restaurant_id==Restaurant.id).where(Restaurant.country=='US',Restaurant.currency=='USD',Restaurant.latitude.is_not(None),Restaurant.longitude.is_not(None),MenuItem.price>0).limit(1)).first()
 if not pair:raise RuntimeError('No US restaurant/menu available for quote-only audit')
 restaurant,menu=pair
 user=User(email='fee-browser-audit-'+secrets.token_hex(8)+'@example.com',password='not-a-login',name='Fee browser audit',role='customer',country='IN')
 db.add(user);db.flush();db.add(Customer(id=user.id));db.flush()
 lat,lng=restaurant.latitude,restaurant.longitude
 first=Address(customer_id=user.id,label='Fee audit near',details='Fee audit near delivery address',country='US',state='Tennessee',city='Nashville',latitude=lat+.001,longitude=lng,is_default=True)
 second=Address(customer_id=user.id,label='Fee audit far',details='Fee audit far delivery address',country='US',state='Tennessee',city='Nashville',latitude=lat+.17,longitude=lng)
 db.add_all([first,second,CartItem(customer_id=user.id,menu_item_id=menu.id,quantity=1),CustomerLocation(customer_id=user.id,latitude=lat+.001,longitude=lng,country='US',address=first.details)]);db.commit()
 data.update(customer_id=user.id,address_ids=[first.id,second.id])
 stamp=datetime.now(timezone.utc)
 token=jwt.encode({'sub':str(user.id),'ver':user.token_version,'iat':stamp,'exp':stamp+timedelta(hours=1),'aud':'dashvanti','iss':'dashvanti-api'},cfg.jwt_secret,algorithm='HS256')
 customer=Store();customer['token']=token;customer['role']='customer';customer['name']=user.name;customer['email']=user.email;customer['order_mode']='delivery';customer['delivery_address_id']=first.id;customer.create()
 data.update(customer_session=customer.session_key,customer_cookie_name='dashvanti_customer')
 # Session cookie names are role-dependent; read the configured customer name independently below.
print(json.dumps(data))
