import os,sys,json
from pathlib import Path
from sqlalchemy import select,delete,or_
import backend.main
import backend.services.session_service
from backend.db import Session,Base
from backend.models import User,Order,AuditEvent
from backend.models_driver_partner import DriverDocument
from backend.config import settings
data=json.loads(Path('deploy/.driver-browser-audit.json').read_text())['driver']
with Session() as db:
 user=db.get(User,data['user_id'])
 assert user and user.email==data['email'] and user.email.startswith('driver-browser-audit-')
 assert not db.scalar(select(Order.id).where(or_(Order.driver_id==user.id,Order.customer_id==user.id,Order.restaurant_id==user.id)).limit(1))
 paths=list(db.scalars(select(DriverDocument.encrypted_path).where(DriverDocument.driver_id==user.id)))
 for table in reversed(Base.metadata.sorted_tables):
  columns=[column for column in table.columns if any(fk.column.table.name in {'users','drivers'} for fk in column.foreign_keys)]
  if columns:db.execute(delete(table).where(or_(*(column==user.id for column in columns))))
 db.execute(delete(AuditEvent).where(AuditEvent.target==str(user.id),AuditEvent.action.like('driver-partner:%')))
 db.execute(delete(User).where(User.id==user.id));db.commit()
 for filename in paths:
  value=Path(filename).resolve();parent=(Path(settings.file_root)/'driver-private'/str(data['user_id'])).resolve()
  assert value.parent==parent
  value.unlink(missing_ok=True)
 print('Browser driver fixture removed')
