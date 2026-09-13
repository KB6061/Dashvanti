import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'frontend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DJANGO_SECRET_KEY'] = 'test-django-secret-with-at-least-32-characters'
os.environ['SESSION_FILE_PATH'] = str(ROOT / '.test-sessions')
os.environ['ALLOWED_HOSTS'] = 'testserver,localhost'
os.environ['COOKIE_SECURE'] = 'false'
import django
django.setup()
from django.test import Client
from django.template.loader import get_template
from django.urls import resolve


def test_templates_compile():
    for template in (ROOT / 'frontend').rglob('*.html'):
        relative = str(template).split('templates' + os.sep)[-1].replace(os.sep, '/')
        get_template(relative)


def test_portal_routes_and_home():
    client = Client()
    assert client.get('/').status_code == 200
    for role in ['customer', 'restaurant', 'driver']:
        for page in ['login', 'register', 'forgot', 'reset']:
            assert client.get(f'/{role}/{page}').status_code == 200
        assert client.get(f'/{role}/orders').status_code == 302
    for url in ['/customer/restaurant/1', '/customer/order/1/track', '/restaurant/menu', '/restaurant/stats', '/driver/earnings']:
        assert resolve(url)


def test_csrf_rejects_untrusted_submission():
    client = Client(enforce_csrf_checks=True)
    assert client.post('/customer/login', {'email':'test@example.com','password':'password'}).status_code == 403


def test_login_and_role_isolation():
    client = Client()
    with patch('common_app.views.call', return_value={'access_token':'test-token','role':'customer'}):
        response = client.post('/customer/login', {'email':'test@example.com','password':'Strong-password-123'})
    assert response.status_code == 302
    assert response.url == '/customer/restaurants'
    assert client.session['token'] == 'test-token'
    assert client.get('/restaurant/orders').status_code == 302
    client.session.flush()
