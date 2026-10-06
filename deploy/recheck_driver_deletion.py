import backend.main
from backend.db import Session
from backend.models import User
from backend.services.operations_service import admin_delete_user
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
with Session() as db:ids=list(db.scalars(select(User.id).where(User.role=='driver')))
for driver_id in ids:
 with Session() as db:
  try:
   admin_delete_user(db,driver_id)
   db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
   print('driver',driver_id,'DELETE validation PASSED; rolled back')
  except IntegrityError as exc:
   print('driver',driver_id,'CONFLICT',str(exc.orig))
  except Exception as exc:
   print('driver',driver_id,'ERROR',type(exc).__name__,str(exc))
  finally:db.rollback()
print('No production drivers deleted.')
