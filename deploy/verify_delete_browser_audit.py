import os,sys,json
from pathlib import Path
from sqlalchemy import select,delete
import backend.main
from backend.db import Session
from backend.config import settings
from backend.models import User,Driver,AuditEvent
from backend.models_driver_partner import DriverPartner,DriverDocument,DriverWithdrawal,DriverInsuranceClaim
from backend.models_driver_agreement import DriverAgreementAcceptance
data=json.loads(Path('deploy/.delete-browser-audit.json').read_text())
assert data['email'].startswith('delete-browser-audit-')
with Session() as db:
 assert db.get(User,data['user_id']) is None and db.get(Driver,data['user_id']) is None
 for model in [DriverPartner,DriverDocument,DriverWithdrawal,DriverInsuranceClaim]:assert not db.scalar(select(model).where(model.driver_id==data['user_id']))
 document=Path(data['document_path']).resolve()
 assert document.parent==(Path(settings.file_root)/'driver-private'/str(data['user_id'])).resolve()
 assert not document.exists()
 db.execute(delete(DriverAgreementAcceptance).where(DriverAgreementAcceptance.driver_temp_id==data['agreement_temp_id'],DriverAgreementAcceptance.driver_id.is_(None)))
 db.execute(delete(AuditEvent).where(AuditEvent.target=='user:'+str(data['user_id']),AuditEvent.action=='admin-user-deleted'))
 db.commit()
 print('Verified permanent database deletion, dependent-row cleanup and encrypted document removal.')
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings as frontend_settings
from importlib import import_module
Store=import_module(frontend_settings.SESSION_ENGINE).SessionStore
Store().delete(data['cookie']['value'])
print('Temporary browser session and audit fixtures removed.')
