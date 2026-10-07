import os,sys,json,jwt
from pathlib import Path
sys.path.insert(0,'frontend');os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
from backend.db import Session
from backend.models import User
from backend.config import settings as cfg
from datetime import datetime,timezone,timedelta
data=json.loads(Path('deploy/fee-browser-audit.json').read_text());Store=import_module(settings.SESSION_ENGINE).SessionStore
Store(session_key=data['customer_session']).delete()
with Session() as db:
 user=db.get(User,data['customer_id']);stamp=datetime.now(timezone.utc)
 token=jwt.encode({'sub':str(user.id),'ver':user.token_version,'iat':stamp,'exp':stamp+timedelta(hours=1),'aud':'dashvanti','iss':'dashvanti-api'},cfg.jwt_secret,algorithm='HS256')
 customer=Store();customer['token']=token;customer['role']='customer';customer['name']=user.name;customer['email']=user.email;customer['order_mode']='delivery';customer['delivery_address_id']=data['address_ids'][0];customer.create()
 data.update(customer_session=customer.session_key,customer_cookie_name=settings.SESSION_COOKIE_NAME)
Path('deploy/fee-browser-audit.json').write_text(json.dumps(data));print(json.dumps(data))
