import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'frontend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.conf import settings
from importlib import import_module
data=json.loads(Path('deploy/.driver-browser-audit.json').read_text())[os.environ['PORTAL_ROLE']]
Store=import_module(settings.SESSION_ENGINE).SessionStore
Store().delete(data['cookie']['value'])
print('Browser session removed:',os.environ['PORTAL_ROLE'])
