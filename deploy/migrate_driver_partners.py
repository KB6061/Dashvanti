import backend.models
import backend.payment_models
import backend.models_driver_partner
from backend.db import Base, engine
from sqlalchemy import text, inspect
names = ['driver_partners','driver_documents','driver_verifications','driver_deposits','driver_wallets','driver_earnings','driver_withdrawals','driver_withdrawal_allocations','driver_incidents','driver_nominees','driver_insurance','driver_insurance_claims','driver_orders','driver_delivery_otps','driver_partner_notices','driver_push_devices']
Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in names])
with engine.begin() as db:
    db.execute(text("ALTER TABLE driver_withdrawals ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''"))
    if not inspect(engine).has_table('driver_ratings'):
        db.execute(text('CREATE VIEW driver_ratings AS SELECT r.id, r.order_id, o.driver_id, r.driver AS rating FROM ratings r JOIN orders o ON o.id=r.order_id WHERE r.driver IS NOT NULL'))
print('Driver partner tables created')
