import os,sys,json,ipaddress
from pathlib import Path
from sqlalchemy import select,delete,or_
import backend.main
from backend.db import Session,Base
from backend.models import User,Order,AuditEvent
from backend.models_driver_agreement import DriverAgreementAcceptance
data=json.loads(Path('deploy/.agreement-browser-audit.json').read_text())
with Session() as db:
 user=db.scalar(select(User).where(User.email==data['email']))
 assert user and user.email.startswith('agreement-browser-audit-')
 row=db.scalar(select(DriverAgreementAcceptance).where(DriverAgreementAcceptance.driver_id==user.id))
 assert row and row.accepted and row.full_legal_name==user.name
 assert row.accepted_at and row.acceptance_timestamp==row.accepted_at and row.registered_at
 assert len(json.loads(row.acknowledgements))==17 and len(row.agreement_hash)==64 and row.agreement_content
 assert row.ip_address and not ipaddress.ip_address(row.ip_address).is_loopback
 assert 'Chrome' in row.browser_information and json.loads(row.device_information)['user_agent']==row.browser_information
 print('Database audit verified: version, signed client IP, browser/device, legal name, timestamps, 17 acknowledgements, document snapshot, driver linkage.')
 assert not db.scalar(select(Order.id).where(or_(Order.driver_id==user.id,Order.customer_id==user.id,Order.restaurant_id==user.id)).limit(1))
 for table in reversed(Base.metadata.sorted_tables):
  columns=[column for column in table.columns if any(fk.column.table.name in {'users','drivers'} for fk in column.foreign_keys)]
  if columns:db.execute(delete(table).where(or_(*(column==user.id for column in columns))))
 db.execute(delete(AuditEvent).where(AuditEvent.target==str(user.id),AuditEvent.action.like('driver-partner:%')))
 db.execute(delete(User).where(User.id==user.id));db.commit()
 assert not db.scalar(select(User.id).where(User.email==data['email']))
 print('Test driver and related database records removed.')
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
Store=import_module(settings.SESSION_ENGINE).SessionStore
for cookie in data['cookies']:
 if cookie['name']==settings.SESSION_COOKIE_NAME:Store().delete(cookie['value'])
print('Browser login session removed.')
