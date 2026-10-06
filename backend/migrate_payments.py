import json
import os
from sqlalchemy import text
from backend.db import Base, engine, Session
from backend.payment_models import Payment, Refund, AdminSettings, PaymentMethod
from backend.services.admin_payment_service import cipher


def main():
    with engine.begin() as connection:
        for table, column, definition in [('users', 'country', 'VARCHAR(2)'), ('restaurants', 'currency', "VARCHAR(3) NOT NULL DEFAULT 'USD'"), ('orders', 'currency', "VARCHAR(3) NOT NULL DEFAULT 'USD'")]:
            connection.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}'))
        Base.metadata.create_all(connection, tables=[table for name, table in Base.metadata.tables.items() if name.startswith('pg_')])
    with Session() as db:
        for name in ('phonepe', 'razorpay', 'cashfree'):
            if not db.get(PaymentMethod, name):
                db.add(PaymentMethod(name=name, enabled=False))
        db.flush()
        method = db.get(PaymentMethod, 'phonepe')
        if not method.settings_id:
            names = ('merchant_id', 'salt_key', 'salt_index', 'api_key', 'client_id', 'client_secret', 'client_version', 'webhook_username', 'webhook_password')
            cfg = {name: os.environ.get('PHONEPE_' + name.upper(), '') for name in names}
            cfg['salt_index'] = int(cfg['salt_index'] or 1)
            cfg['client_version'] = int(cfg['client_version'] or 1)
            row = AdminSettings(environment='sandbox', api_version=os.environ.get('PHONEPE_API_VERSION', 'v2'), encrypted_credentials=cipher().encrypt(json.dumps(cfg).encode()).decode())
            db.add(row)
            db.flush()
            method.settings_id = row.id
        db.commit()
    print('Payment tables and country/currency fields ready; all gateways disabled by default')


if __name__ == '__main__':
    main()
