from pathlib import Path
import secrets
from cryptography.fernet import Fernet

path = Path('.env')
source = path.read_text() if path.exists() else ''
defaults = {'PAYMENT_ENCRYPTION_KEY': Fernet.generate_key().decode(),
    'PAYMENT_PROXY_SECRET': secrets.token_hex(32), 'PHONEPE_API_VERSION': 'v2'}
for name, value in defaults.items():
    if not any(line.startswith(name + '=') and line.split('=', 1)[1].strip() for line in source.splitlines()):
        source += '\n' + name + '=' + value + '\n'
path.write_text(source)
path.chmod(0o600)
print('Payment environment keys ready; existing keys preserved')
