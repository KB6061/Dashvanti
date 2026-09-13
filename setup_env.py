from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
output = root / '.env'
if output.exists():
    raise SystemExit('.env already exists; refusing to overwrite')
password = secrets.token_urlsafe(24)
text = (root / '.env.example').read_text(encoding='utf-8-sig')
text = text.replace('replace-with-at-least-32-random-characters', secrets.token_urlsafe(48))
text = text.replace('replace-with-another-long-random-secret', secrets.token_urlsafe(48))
text = text.replace('replace-local-oracle-password', secrets.token_urlsafe(24))
text = text.replace('change-me', password)
with output.open('x', encoding='utf-8') as stream:
    stream.write(text)
print('Created local .env with unique secrets. Keep it private.')
