from datetime import date, datetime
from fastapi import APIRouter, Depends, Request, Query, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from backend.db import get_db
from backend.security import current_user, optional_user, role
from backend.models import User
from backend.account_enhancement_models import EnterpriseAudit, EntityVerification
from backend.account_enhancement_schemas import TicketInput, TicketAction, FavoriteInput, WalletInput, WalletTransfer, GatewayInput, ReviewInput, ReviewAction, LocationInput, RollbackInput, VerificationInput, RegionInput
from backend.services import incident_service as incidents, account_experience_service as experience, wallet_funding_service as wallet, account_gateway_service as gateways, enterprise_audit_service as audits

router = APIRouter(prefix='/account-experience', tags=['Account experience'])
customer = role('customer')
admin = role('admin')


@router.get('/identity')
def identity(user=Depends(current_user), db=Depends(get_db, scope='function')):
    from backend.models import CustomerLocation
    return {'id': user.id, 'name': user.name, 'role': user.role, 'avatar': experience.avatar(db, user.id)['url'],
            'verified': experience.verified(db, user.id),'location_needed':user.role=='customer' and not db.get(CustomerLocation,user.id)}


from backend.account_enhancement_schemas import WalletRefundInput
from backend.account_enhancement_schemas import AdminLoginInput
from backend.account_enhancement_schemas import SLAInput


@router.get('/admin/support-sla')
def support_sla(user=Depends(admin),db=Depends(get_db,scope='function')):
    from backend.models import SystemConfig
    return [{'priority':priority,'minutes':int(row.value) if (row:=db.get(SystemConfig,'support.sla_minutes.'+priority.lower())) else None} for priority in ('Low','Medium','High','Critical','Emergency')]


@router.post('/admin/support-sla')
def update_support_sla(data:SLAInput,user=Depends(admin),db=Depends(get_db,scope='function')):
    incidents.permission(db,user,'support_edit')
    from backend.models import SystemConfig
    key='support.sla_minutes.'+data.priority.lower()
    row=db.get(SystemConfig,key)
    if not row:row=SystemConfig(key=key);db.add(row)
    row.value=str(data.minutes)
    db.info['audit_reason']=data.reason
    return {'message':'SLA policy saved for new tickets'}


@router.post('/admin/sign-in')
def admin_sign_in(data: AdminLoginInput,request: Request,db=Depends(get_db,scope='function')):
    import hashlib,secrets
    from backend.services.account_location_service import client_ip
    from backend.services.redis_geo_service import client
    try:
        redis=client();key='account:admin-login:'+hashlib.sha256(client_ip(request).encode()).hexdigest()
        attempts=redis.incr(key)
        if attempts==1:redis.expire(key,300)
    except Exception:raise HTTPException(503,'Sign in temporarily unavailable')
    if attempts>10:raise HTTPException(429,'Too many sign in attempts. Try again later.')
    if not data.email.strip():
        from backend.config import settings
        from backend.models import User
        from backend.services.session_service import issue_tokens
        if not settings.admin_secret or not secrets.compare_digest(data.password,settings.admin_secret):raise HTTPException(401,'Invalid credentials')
        user=db.scalar(select(User).where(User.email=='system-admin@dashvanti.invalid',User.role=='admin'))
        if not user:raise HTTPException(409,'Configure an administrator account first')
        request.state.audit_actor={'id':user.id,'name':user.name,'role':user.role,'ip':client_ip(request),'device':request.headers.get('user-agent','')[:500]}
        audits.record(db,request.state.audit_actor,'sign-in','authentication',{'id':user.id},{},{})
        return issue_tokens(user)
    from backend.services.auth_service import login
    return login(db,data,request)


@router.post('/admin/wallet-refunds')
def wallet_refund(data: WalletRefundInput,user=Depends(admin),db=Depends(get_db,scope='function')):
    from backend.services.wallet_refund_service import credit
    return credit(db,user,data)


@router.get('/avatar/{user_id}')
def avatar(user_id: int, user=Depends(optional_user), db=Depends(get_db, scope='function')):
    return FileResponse(experience.avatar_file(db, user, user_id), media_type='image/jpeg', headers={'Cache-Control': 'private, no-cache'})


@router.get('/states/{country}')
def states(country: str):
    from backend.services.account_location_service import STATES
    return {'country': country, 'states': STATES.get(country.upper(), [])}


@router.get('/review-photo/{file_id}')
def review_photo(file_id: int, user=Depends(optional_user), db=Depends(get_db, scope='function')):
    return FileResponse(experience.review_photo(db,user,file_id), media_type='image/jpeg', headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'})


@router.post('/location')
def location(data: LocationInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    from backend.services.account_location_service import detect
    return detect(db, user, data)


@router.get('/favorites')
def favorites(user=Depends(customer), db=Depends(get_db, scope='function')):
    return experience.favorites(db, user)


@router.post('/favorites')
def favorite(data: FavoriteInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return experience.favorite(db, user, data)


@router.get('/gateways')
def methods(user=Depends(current_user), db=Depends(get_db, scope='function')):
    return {'gateways': gateways.methods(db, user)}


@router.get('/admin/gateways')
def admin_gateways(user=Depends(admin), db=Depends(get_db, scope='function')):
    return {'gateways': gateways.methods(db, admin=True)}


@router.post('/admin/gateways')
def set_gateway(data: GatewayInput, user=Depends(admin), db=Depends(get_db, scope='function')):
    return gateways.update(db, user, data)


@router.post('/wallet/funding')
def funding(data: WalletInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return wallet.begin(db, user, data)


@router.post('/wallet/funding/{funding_id}/verify')
def verify_funding(funding_id: str, user=Depends(customer), db=Depends(get_db, scope='function')):
    return wallet.complete(db, user, funding_id)


@router.post('/wallet/transfer')
def transfer(data: WalletTransfer, user=Depends(customer), db=Depends(get_db, scope='function')):
    return wallet.transfer(db, user, data)


@router.get('/wallet/checkout/{funding_id}')
def wallet_checkout(funding_id: str, user=Depends(customer), db=Depends(get_db, scope='function')):
    from backend.services.wallet_provider_service import checkout
    return checkout(db,user,funding_id)


@router.get('/rewards')
def customer_rewards(user=Depends(customer),db=Depends(get_db,scope='function')):
    from backend.customer_account_models import CustomerReward
    return [{'points':row.points,'description':row.description,'created_at':row.created_at} for row in db.scalars(select(CustomerReward).where(CustomerReward.customer_id==user.id).order_by(CustomerReward.created_at.desc()).limit(8))]


@router.post('/wallet/callback/{provider}')
async def wallet_callback(provider: str, request: Request, db=Depends(get_db, scope='function')):
    from backend.services.wallet_webhook_service import receive,read_body
    return receive(db,provider,await read_body(request),request.headers)


@router.get('/tickets')
def tickets(q: str = Query('', max_length=120), status: str = '', priority: str = '', category: str = '',
            assignee_id: int | None = None, customer_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
            sort: str = 'updated', direction: str = 'desc', page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
            export: bool = False, user=Depends(current_user), db=Depends(get_db, scope='function')):
    values = dict(q=q, status_filter=status, priority=priority, category=category, assignee_id=assignee_id,
                  date_from=date_from, date_to=date_to, sort=sort, direction=direction, page=page, size=size, customer_id=customer_id)
    result = incidents.listing(db, user, **values)
    if export:
        # Export the selected page; broad exports cannot bypass ownership or filters.
        return Response(incidents.csv_export(result['items']), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="dashvanti-incidents.csv"', 'Cache-Control': 'no-store'})
    return result


@router.post('/tickets', status_code=201)
def create_ticket(data: TicketInput, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return incidents.create(db, user, data)


@router.get('/tickets/{ticket_id}')
def ticket(ticket_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return incidents.public_ticket(db, incidents.owned(db, user, ticket_id), user, True)


@router.post('/tickets/{ticket_id}')
def change_ticket(ticket_id: int, data: TicketAction, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return incidents.change(db, user, ticket_id, data)


@router.post('/tickets/{ticket_id}/attachments')
def attachment(ticket_id: int, file: UploadFile = File(...), internal: bool = Form(False), user=Depends(current_user), db=Depends(get_db, scope='function')):
    return incidents.upload(db, user, ticket_id, file, internal)


@router.get('/attachments/{attachment_id}')
def download_attachment(attachment_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    row, path = incidents.attachment(db, user, attachment_id)
    return FileResponse(path, media_type=row.mime, filename=row.name, content_disposition_type='attachment', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/admin/assignees')
def assignees(user=Depends(admin), db=Depends(get_db, scope='function')):
    return [{'id': row.id, 'name': row.name} for row in db.scalars(select(User).where(User.role == 'admin').order_by(User.name))]


@router.get('/reviews')
def reviews(restaurant_id: int | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100), db=Depends(get_db, scope='function')):
    return experience.reviews(db, restaurant_id, page=page, size=size)


@router.post('/reviews')
def review(data: ReviewInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return experience.review_save(db, user, data)


@router.post('/reviews/{review_id}')
def review_action(review_id: int, data: ReviewAction, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return experience.review_action(db, user, review_id, data)


@router.get('/admin/reviews')
def admin_reviews(page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100), user=Depends(admin), db=Depends(get_db, scope='function')):
    return experience.reviews(db, admin=True, page=page, size=size)


@router.post('/admin/verification')
def verification(data: VerificationInput, user=Depends(admin), db=Depends(get_db, scope='function')):
    incidents.permission(db, user, 'review_moderate')
    target = db.get(User, data.user_id)
    if not target or target.role not in {'customer', 'driver', 'restaurant'}:
        raise HTTPException(404, 'Account not found')
    row = db.get(EntityVerification, target.id)
    if not row:
        row = EntityVerification(user_id=target.id)
        db.add(row)
    row.verified, row.moderator_id, row.reason, row.updated_at = data.verified, user.id, data.reason, datetime.utcnow()
    db.info['audit_reason'] = data.reason
    return {'verified': row.verified}


@router.post('/admin/regions/{kind}')
def region(kind: str, data: RegionInput, user=Depends(admin), db=Depends(get_db, scope='function')):
    from backend.models import Restaurant,Promotion
    from backend.account_enhancement_models import RestaurantRegion,PromotionRegion
    from backend.services.account_location_service import STATES
    incidents.permission(db,user,'gateway_edit')
    if data.state and data.state not in STATES[data.country]:
        raise HTTPException(422,'State does not belong to this country')
    if kind=='restaurant':
        target=db.get(Restaurant,data.id)
        if not target or target.country!=data.country or not data.city.strip():
            raise HTTPException(422,'Choose an existing restaurant in this country and enter its city')
        row=db.get(RestaurantRegion,data.id)
        if not row:row=RestaurantRegion(restaurant_id=data.id,city=data.city.strip());db.add(row)
        row.city,row.state=data.city.strip(),data.state
    elif kind=='promotion':
        if not db.get(Promotion,data.id):raise HTTPException(404,'Promotion not found')
        row=db.get(PromotionRegion,data.id)
        if not row:row=PromotionRegion(promotion_id=data.id,country=data.country);db.add(row)
        row.country,row.city=data.country,data.city.strip()
    else:raise HTTPException(404,'Region type not found')
    db.info['audit_reason']=data.reason
    return {'message':'Location scope saved'}


@router.get('/admin/audit')
def audit(q: str = Query('', max_length=120), admin_id: int | None = None, module: str = '', action: str = '', status: str = '',
          date_from: date | None = None, date_to: date | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
          export: bool = False, user=Depends(admin), db=Depends(get_db, scope='function')):
    result = audits.listing(db, q, admin_id, module, action, status, date_from, date_to, page, size)
    if export:
        return JSONResponse(jsonable_encoder(result), headers={'Content-Disposition': 'attachment; filename="dashvanti-admin-audit.json"', 'Cache-Control': 'no-store'})
    return result


@router.get('/admin/audit/{audit_id}')
def audit_detail(audit_id: int, user=Depends(admin), db=Depends(get_db, scope='function')):
    row = db.get(EnterpriseAudit, audit_id)
    if not row:
        raise HTTPException(404, 'Audit record not found')
    return audits.detail(row)


@router.post('/admin/audit/{audit_id}/rollback')
def rollback(audit_id: int, data: RollbackInput, user=Depends(admin), db=Depends(get_db, scope='function')):
    return audits.rollback(db, user, audit_id, data.reason)
