import os,sys,json,secrets
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'frontend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
Store=import_module(settings.SESSION_ENGINE).SessionStore
data={}
if os.environ['PORTAL_ROLE']=='driver':
 from backend.db import Session
 from backend.models import User,Driver
 from backend.models_driver_partner import DriverPartner
 from backend.services.session_service import issue_tokens
 with Session() as db:
  user=User(email='driver-browser-audit-'+secrets.token_hex(8)+'@example.com',name='Driver partner browser audit',password='not-a-real-password',role='driver',country='IN')
  db.add(user);db.flush();db.add(Driver(id=user.id,online=False));db.flush();db.add(DriverPartner(driver_id=user.id));db.commit()
  tokens=issue_tokens(user)
  data={'user_id':user.id,'email':user.email}
  session=Store();session['token']=tokens['access_token'];session['refresh_token']=tokens['refresh_token'];session['role']='driver';session['name']=user.name;session['user_id']=user.id
else:
 session=Store();session['admin_authenticated']=True
session.create()
data['cookie']={'name':settings.SESSION_COOKIE_NAME,'value':session.session_key,'domain':os.environ['PORTAL_ROLE']+'.dashvanti.com','path':'/','secure':True,'httpOnly':True,'sameSite':'Lax'}
print(json.dumps(data))
