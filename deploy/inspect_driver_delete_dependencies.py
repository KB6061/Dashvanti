import backend.main
from backend.db import engine,Base
from sqlalchemy import inspect
ins=inspect(engine)
for table in ins.get_table_names():
 for fk in ins.get_foreign_keys(table):
  if fk['referred_table'] in ['users','drivers','driver_withdrawals','driver_incidents','pg_payments','pg_refunds','payout_transactions']:
   print(table,fk['constrained_columns'],'->',fk['referred_table'],fk['options'])
print('Payment model columns')
for name in ['pg_payments','pg_refunds','pg_logs','pg_webhooks','refresh_sessions']:
 if ins.has_table(name):print(name,[(c['name'],c['nullable']) for c in ins.get_columns(name)])
