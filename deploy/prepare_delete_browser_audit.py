import os,sys,json,secrets,io
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
from backend.db import Session
from backend.models import User,Driver
from backend.models_driver_partner import DriverPartner,DriverIncident,DriverInsuranceClaim,DriverWithdrawal,DriverDocument
from backend.services import driver_agreement_service as agreement, driver_partner_service as partner
from backend.schemas_driver_agreement import AgreementRead,AgreementAccept
from types import SimpleNamespace
from PIL import Image
with Session() as db:
 user=User(email='delete-browser-audit-'+secrets.token_hex(8)+'@example.com',name='Delete Browser Audit',password='not-a-login',role='driver')
 db.add(user);db.flush();db.add(Driver(id=user.id,online=False));db.flush();db.add(DriverPartner(driver_id=user.id));db.flush()
 value=agreement.start(db,user);agreement.record_read(db,value['token'],AgreementRead(agreement_version=value['agreement_version'],scroll_completed=True),user)
 agreement.accept(db,value['token'],AgreementAccept(agreement_version=value['agreement_version'],full_legal_name=user.name,acknowledgements={item['key']:True for item in value['acknowledgements']}),{},user)
 image=io.BytesIO();Image.new('RGB',(40,40),(30,90,50)).save(image,'PNG');image.seek(0)
 document=partner.upload(db,user,'selfie',SimpleNamespace(file=image))
 incident=DriverIncident(driver_id=user.id,kind='Other',description='Browser delete audit');db.add(incident);db.flush()
 db.add_all([DriverInsuranceClaim(driver_id=user.id,incident_id=incident.id,reference='audit-'+secrets.token_hex(12),amount=10),DriverWithdrawal(driver_id=user.id,request_key=secrets.token_hex(12),amount=10,currency='INR',method='BANK')]);db.commit()
 data={'user_id':user.id,'email':user.email,'document_id':document['id'],'document_path':db.get(DriverDocument,document['id']).encrypted_path,'agreement_temp_id':value['driver_temp_id']}
Store=import_module(settings.SESSION_ENGINE).SessionStore
session=Store();session['admin_authenticated']=True;session.create()
data['cookie']={'name':settings.SESSION_COOKIE_NAME,'value':session.session_key,'domain':'admin.dashvanti.com','path':'/','secure':True,'httpOnly':True,'sameSite':'Lax'}
print(json.dumps(data))
