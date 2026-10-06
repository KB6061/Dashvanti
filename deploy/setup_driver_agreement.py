import os,secrets
from pathlib import Path
import backend.models
from backend.db import engine
from backend.models_driver_agreement import DriverAgreementAcceptance
DriverAgreementAcceptance.__table__.create(engine,checkfirst=True)
env=Path('.env');body=env.read_text()
if not os.getenv('DRIVER_AGREEMENT_PROXY_SECRET'):
 with env.open('a') as stream:stream.write('\nDRIVER_AGREEMENT_PROXY_SECRET='+secrets.token_urlsafe(48)+'\n')
print('Consent audit table and signed proxy configuration ready')
