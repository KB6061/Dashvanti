import os,sys,json
sys.path.insert(0,'frontend');os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.test import Client
from django.conf import settings
from pathlib import Path
data=json.loads(Path('deploy/fee-browser-audit.json').read_text())
client=Client();client.cookies[settings.SESSION_COOKIE_NAME]=data['customer_session']
response=client.get('/customer/checkout',HTTP_HOST='customer.dashvanti.com',secure=True)
print(response.status_code)
