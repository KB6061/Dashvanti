from fastapi import APIRouter,Depends,HTTPException
from backend.db import get_db
from backend.security import current_user,admin_secret
from backend.services.gps_auth_service import ticket
from backend.services.order_service import owned
from backend.gps_config import FINAL

router=APIRouter(prefix='/gps',tags=['GPS streaming'])

@router.post('/ticket')
def user_ticket(order_id:int|None=None,user=Depends(current_user),db=Depends(get_db,scope='function')):
    if order_id:
        order=owned(db,user,order_id)
        if order.status in FINAL:raise HTTPException(409,'Historical orders do not have live GPS')
        return ticket('order',user,order_id)
    if user.role not in {'driver','restaurant','customer'}:raise HTTPException(403,'Portal user required')
    return ticket(user.role,user)

@router.post('/admin-ticket',dependencies=[Depends(admin_secret)])
def admin_ticket():
    return ticket('admin')
