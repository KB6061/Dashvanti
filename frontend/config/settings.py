import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = False
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS','localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS','http://localhost:8000').split(',')
INSTALLED_APPS = ['django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','common_app','customer_app','restaurant_app','driver_app','admin_app']
MIDDLEWARE = ['common_app.middleware.UIActivityLogMiddleware','django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','common_app.middleware.PortalScopeMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.messages.context_processors.messages','common_app.context.portal']}}]
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':'/tmp/dashvanti-unused.db'}}
# Server-side file sessions keep API bearer tokens out of browser-readable cookies.
SESSION_ENGINE = 'django.contrib.sessions.backends.file'
SESSION_FILE_PATH = os.environ.get('SESSION_FILE_PATH',str(BASE_DIR.parent/'run'/'sessions'))
Path(SESSION_FILE_PATH).mkdir(parents=True, exist_ok=True, mode=0o700)
PORTAL_ROLE = os.environ.get('PORTAL_ROLE','')
SESSION_COOKIE_NAME = f'dashvanti_{PORTAL_ROLE or "main"}_sessionid'
CSRF_COOKIE_NAME = f'dashvanti_{PORTAL_ROLE or "main"}_csrftoken'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.environ.get('COOKIE_SECURE','true').lower() == 'true'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE','34560000'))
SESSION_SAVE_EVERY_REQUEST = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
STATICFILES_DIRS = [BASE_DIR/'static', BASE_DIR/'logo']
API_URL = os.environ.get('API_URL','http://api:8001') + '/api'
DJANGO_ACTIVITY_LOG = os.environ.get('DJANGO_ACTIVITY_LOG', str(BASE_DIR.parent/'logs'/'ui-activity.log'))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD','krishna')
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY','')
PORTAL_URLS = {
    'customer': os.environ.get('CUSTOMER_URL','http://192.168.56.101:8080'),
    'restaurant': os.environ.get('RESTAURANT_URL','http://192.168.56.101:8081'),
    'driver': os.environ.get('DRIVER_URL','http://192.168.56.101:8082'),
    'admin': os.environ.get('ADMIN_URL','http://192.168.56.101:8083'),
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_MEMORY_SIZE = 6*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5*1024*1024
USE_TZ = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'quiet': {'class': 'logging.NullHandler'}},
    'loggers': {name: {'handlers': ['quiet'], 'propagate': False}
                for name in ('django.server', 'django.request', 'django.security')},
}
