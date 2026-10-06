import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'frontend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.template.loader import get_template
for name in ['driver_app/partner.html','admin_app/driver_partners.html','admin_app/driver_partner_detail.html','admin_app/driver_partner_reports.html','admin_app/driver_manager_login.html','order.html']:
    get_template(name)
    print('Template valid:', name)
