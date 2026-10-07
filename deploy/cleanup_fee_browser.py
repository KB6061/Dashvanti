import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
from sqlalchemy import delete
from backend.db import Session
from backend.models import User,Customer,CustomerLocation,Address,CartItem,AuditEvent
from backend.delivery_fee_models import Country,CountryDeliverySettings,DeliverySurgeRule
data=json.loads(Path('deploy/fee-browser-audit.json').read_text())
with Session() as db:
 for model in (DeliverySurgeRule,CountryDeliverySettings,Country):db.execute(delete(model).where(model.country_code=='ZZ'))
 db.execute(delete(AuditEvent).where(AuditEvent.action.in_(['delivery-country-saved','delivery-settings-saved','delivery-surge-saved']),AuditEvent.target.like('ZZ%')))
 uid=data['customer_id']
 for model in (CartItem,Address,CustomerLocation):db.execute(delete(model).where(model.customer_id==uid))
 db.execute(delete(Customer).where(Customer.id==uid));db.execute(delete(User).where(User.id==uid));db.commit()
Store=import_module(settings.SESSION_ENGINE).SessionStore
for key in (data['admin_session'],data['customer_session']):Store(session_key=key).delete()
Path('deploy/fee-browser-audit.json').unlink(missing_ok=True)
print('Browser audit users, sessions, cart and pricing removed')
