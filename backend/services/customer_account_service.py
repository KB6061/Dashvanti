import os, json, secrets, hashlib, base64, hmac, struct, time
from datetime import timedelta, date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import quote
import httpx, jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, func, delete, update
from backend.config import settings
from backend.models import User, Customer, Address, Order, Rating, Review, Restaurant, RestaurantPresentation, Promotion, SupportTicket, File, SystemConfig, now
from backend.customer_account_models import CustomerProfile, CustomerAddressDetails, CustomerFavorite, CustomerWallet, CustomerWalletTransaction, CustomerPaymentMethod, CustomerReward, CustomerCoupon, CustomerReferral, CustomerNotificationSettings, CustomerSupportReply, CustomerLoginHistory, CustomerDevice, CustomerSecurity

NOTIFICATION_FIELDS=('order_updates','delivery_alerts','sms','email','push','promotions','referral_rewards','system_alerts')
CATEGORIES=('Missing Item','Wrong Item','Refund Request','Late Delivery','Payment Issue','Restaurant Issue','Driver Issue','Technical Problem')
LEGAL=(('terms','Terms & Conditions'),('privacy','Privacy Policy'),('refund','Refund Policy'),('cancellation','Cancellation Policy'),('delivery','Delivery Policy'),('cookies','Cookie Policy'))

def record(db, model, user):
    row=db.get(model,user.id)
    if not row:
        row=model(customer_id=user.id)
        if model is CustomerProfile:
            first,_,last=user.name.partition(' ');row.first_name=first;row.last_name=last
            row.timezone='Asia/Kolkata' if user.country=='IN' else 'America/Chicago'
        if model is CustomerReferral:row.code='DV'+secrets.token_hex(6).upper()
        db.add(row);db.flush()
    return row

def owned(db,model,uid,user,key='customer_id'):
    row=db.get(model,int(uid))
    if not row or getattr(row,key)!=user.id:raise HTTPException(404,'Record not found')
    return row

def fields(row,names):
    return {name:getattr(row,name,None) for name in names}

def currency(user):
    return ('INR','₹') if user.country=='IN' else ('USD','$')

def config(db,key,default='0'):
    row=db.get(SystemConfig,'customer_account.'+key)
    return row.value if row else default

def audit_login(db,user,provider,request=None):
    if user.role!='customer':return
    profile=record(db,CustomerProfile,user)
    agent=(request.headers.get('user-agent','') if request else '')[:500]
    ip=request.client.host if request and request.client else ''
    db.add(CustomerLoginHistory(customer_id=user.id,provider=provider,ip_address=ip[:80],user_agent=agent))
    if agent:
        fingerprint=hashlib.sha256(agent.encode()).hexdigest()
        device=db.scalar(select(CustomerDevice).where(CustomerDevice.customer_id==user.id,CustomerDevice.fingerprint==fingerprint))
        if not device:db.add(CustomerDevice(customer_id=user.id,fingerprint=fingerprint,information=agent))
        else:device.last_seen=now()

def snapshot(db,user):
    profile=record(db,CustomerProfile,user);preferences=record(db,CustomerNotificationSettings,user);security=record(db,CustomerSecurity,user)
    curr,symbol=currency(user)
    orders=list(db.scalars(select(Order).where(Order.customer_id==user.id).order_by(Order.id.desc())))
    addresses=list(db.scalars(select(Address).where(Address.customer_id==user.id).order_by(Address.is_default.desc(),Address.id)))
    favorites=[]
    for store in db.scalars(select(Restaurant).join(CustomerFavorite,CustomerFavorite.restaurant_id==Restaurant.id).where(CustomerFavorite.customer_id==user.id)):
        presentation=db.get(RestaurantPresentation,store.id)
        rating=db.scalar(select(func.avg(Rating.restaurant)).join(Order,Order.id==Rating.order_id).where(Order.restaurant_id==store.id))
        photo=(presentation.cover_file_id or presentation.logo_file_id) if presentation else None
        favorites.append({'id':store.id,'name':store.name,'cuisine':store.cuisine,'rating':float(rating or 0),'delivery_minutes':store.delivery_minutes,'photo_id':photo})
    promotions=list(db.scalars(select(Promotion).where(Promotion.enabled==True, (Promotion.starts_at==None)|(Promotion.starts_at<=now()),(Promotion.ends_at==None)|(Promotion.ends_at>now()))))
    from backend.services.account_experience_service import promotion_allowed
    promotions=[row for row in promotions if promotion_allowed(db,row,user)]
    wallet=db.get(CustomerWallet,(user.id,curr));transactions=list(db.scalars(select(CustomerWalletTransaction).where(CustomerWalletTransaction.customer_id==user.id,CustomerWalletTransaction.currency==curr).order_by(CustomerWalletTransaction.id.desc()).limit(100)))
    rewards=list(db.scalars(select(CustomerReward).where(CustomerReward.customer_id==user.id).order_by(CustomerReward.id.desc()).limit(100)))
    points=db.scalar(select(func.coalesce(func.sum(CustomerReward.points),0)).where(CustomerReward.customer_id==user.id))
    referral=db.get(CustomerReferral,user.id)
    if not referral:referral=CustomerReferral(customer_id=user.id,code='DV'+secrets.token_hex(6).upper());db.add(referral);db.flush()
    reviews=[]
    for review,order,store in db.execute(select(Review,Order,Restaurant).join(Order,Order.id==Review.order_id).join(Restaurant,Restaurant.id==Order.restaurant_id).where(Review.customer_id==user.id).order_by(Review.id.desc())):
        rating=db.scalar(select(Rating).where(Rating.order_id==order.id))
        from backend.account_enhancement_models import ReviewPublication
        publication=db.get(ReviewPublication,review.id)
        reviews.append({'title':publication.title if publication else '', 'publication_status':publication.status if publication else 'pending','id':review.id,'order_id':order.id,'restaurant':store.name,'text':review.text,'restaurant_rating':rating.restaurant if rating else None,'driver_rating':rating.driver if rating else None})
    tickets=[]
    for ticket in db.scalars(select(SupportTicket).where(SupportTicket.user_id==user.id).order_by(SupportTicket.id.desc()).limit(100)):
        tickets.append({**fields(ticket,['id','order_id','subject','description','status','resolution','created_at']), 'replies':[fields(row,['id','body','created_at']) for row in db.scalars(select(CustomerSupportReply).where(CustomerSupportReply.ticket_id==ticket.id).order_by(CustomerSupportReply.id))]})
    photo=db.scalar(select(File.id).where(File.user_id==user.id,File.purpose=='profile').order_by(File.id.desc()))
    logins=list(db.scalars(select(CustomerLoginHistory).where(CustomerLoginHistory.customer_id==user.id).order_by(CustomerLoginHistory.id.desc()).limit(30)))
    from backend.models import PlatformContent
    policies={key:(db.get(PlatformContent,'legal_'+key).description if db.get(PlatformContent,'legal_'+key) and db.get(PlatformContent,'legal_'+key).enabled else '') for key,_ in LEGAL}
    from backend.services.account_experience_service import snapshot_extra
    extra=snapshot_extra(db,user)
    return {**extra, 'user':fields(user,['id','name','email','phone','country']), 'profile':{**fields(profile,['first_name','last_name','date_of_birth','gender','language','state','city','timezone','timezone_detected','theme','created_at']),'photo_id':photo,'account_status':'Deletion requested' if security.deletion_requested_at else 'Active'},
        'currency':curr,'symbol':symbol,'stats':{'total_orders':len(orders),'favorites':len(favorites),'addresses':len(addresses),'balance':wallet.balance if wallet else Decimal(0),'coupons':len(promotions),'last_order_at':orders[0].created_at if orders else None},
        'addresses':[{**fields(row,['id','label','details','is_default','country','city','state','latitude','longitude']),**(fields(db.get(CustomerAddressDetails,row.id),['address_type','apartment','landmark','zip_code','instructions']) if db.get(CustomerAddressDetails,row.id) else {})} for row in addresses],
        'orders':[{**fields(order,['id','status','created_at','total','currency','payment_mode','address']), 'restaurant_name':db.get(Restaurant,order.restaurant_id).name if db.get(Restaurant,order.restaurant_id) else 'Restaurant','active':order.status not in {'DELIVERED','CANCELLED','CANCELED','REJECTED','REFUNDED'}} for order in orders],
        'favorites':favorites,'coupons':[fields(row,['id','code','title','description','percent','minimum','cap','ends_at','first_order_only']) for row in promotions], 'wallet_transactions':[fields(row,['id','currency','amount','kind','reference','description','created_at']) for row in transactions],
        'wallet_balances':[fields(row,['currency','balance']) for row in db.scalars(select(CustomerWallet).where(CustomerWallet.customer_id==user.id))],
        'reward_points':points,'rewards':[fields(row,['points','description','created_at']) for row in rewards], 'reward_value':config(db,'reward_value_'+curr),
        'payment_methods':[fields(row,['id','provider','brand','last4','exp_month','exp_year','is_default']) for row in db.scalars(select(CustomerPaymentMethod).where(CustomerPaymentMethod.customer_id==user.id))],
        'card_setup_available':bool(os.environ.get('STRIPE_SECRET_KEY')) and any(item['name']=='stripe' for item in extra['gateways']),'reviews':reviews,'notifications':fields(preferences,NOTIFICATION_FIELDS),'tickets':tickets,'support_categories':CATEGORIES,
        'security':{'two_factor_enabled':security.totp_enabled,'deletion_requested_at':security.deletion_requested_at,'last_login':logins[0].created_at if logins else None},
        'login_history':[fields(row,['provider','ip_address','user_agent','created_at']) for row in logins], 'devices':[fields(row,['id','information','last_seen']) for row in db.scalars(select(CustomerDevice).where(CustomerDevice.customer_id==user.id))],
        'referral':{'code':referral.code,'count':db.scalar(select(func.count()).select_from(CustomerReferral).where(CustomerReferral.referred_by==user.id)), 'earnings':db.scalar(select(func.coalesce(func.sum(CustomerWalletTransaction.amount),0)).where(CustomerWalletTransaction.customer_id==user.id,CustomerWalletTransaction.currency==curr,CustomerWalletTransaction.kind=='referral')),'link':'https://customer.dashvanti.com/customer/register?ref='+referral.code},
        'legal':[{'key':key,'title':title,'content':policies[key]} for key,title in LEGAL]}

def save_profile(db,user,data):
    profile=record(db,CustomerProfile,user)
    if data.country != user.country:
        raise HTTPException(422,'Country is detected from your delivery address. Change the delivery address first.')
    from backend.services.account_location_service import STATES
    if data.state and data.state not in STATES.get(data.country,[]):
        raise HTTPException(422,'Choose a state for your country')
    try:ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:raise HTTPException(422,'Choose a valid timezone')
    if data.date_of_birth and data.date_of_birth>date.today():raise HTTPException(422,'Date of birth cannot be in the future')
    if data.gender not in {'female','male','other','prefer_not_to_say'}:raise HTTPException(422,'Choose a valid gender')
    if str(data.email).lower()!=user.email.lower() or data.phone!=(user.phone or ''):
        reauthenticate(user,data.current_password)
    if db.scalar(select(User.id).where(User.email==str(data.email).lower(),User.id!=user.id)):raise HTTPException(409,'Email already registered')
    # Country/currency changes cannot convert existing wallet balances.
    for name in ('first_name','last_name','date_of_birth','gender','language','state','city','timezone','theme'):setattr(profile,name,getattr(data,name))
    profile.timezone_detected=True
    user.name=(data.first_name+' '+data.last_name).strip()[:120];user.email=str(data.email).lower();user.phone=data.phone;user.country=data.country
    return {'message':'Profile saved','name':user.name}

def reauthenticate(user,password):
    from backend.services.auth_service import passwords
    if not password or not passwords.verify(password,user.password):raise HTTPException(403,'Enter your current password to confirm this action. Google-only accounts can set a password using Forgot password.')

def wallet_credit(db,user,amount,kind,reference,description):
    curr,_=currency(user)
    db.scalar(select(Customer).where(Customer.id==user.id).with_for_update())
    if db.scalar(select(CustomerWalletTransaction.id).where(CustomerWalletTransaction.reference==reference)):return
    wallet=db.get(CustomerWallet,(user.id,curr))
    if not wallet:wallet=CustomerWallet(customer_id=user.id,currency=curr,balance=Decimal(0));db.add(wallet)
    wallet.balance+=amount
    db.add(CustomerWalletTransaction(customer_id=user.id,currency=curr,amount=amount,kind=kind,reference=reference,description=description))

def crypt():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('customer-totp:'+settings.jwt_secret).encode()).digest()))

def verify_totp(db,user,code):
    row=db.scalar(select(CustomerSecurity).where(CustomerSecurity.customer_id==user.id).with_for_update())
    if not row or not row.totp_secret:raise HTTPException(403,'Authenticator is not configured')
    secret=base64.b32decode(crypt().decrypt(row.totp_secret.encode()))
    step=int(time.time()//30)
    for value in range(step-1,step+2):
        digest=hmac.new(secret,struct.pack('>Q',value),hashlib.sha1).digest();offset=digest[-1]&15
        expected=str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
        if hmac.compare_digest(str(code),expected) and value>row.last_totp_step:row.last_totp_step=value;return True
    raise HTTPException(403,'Invalid or already used authenticator code')

def second_factor(db,user,provider,request=None):
    row=db.get(CustomerSecurity,user.id) if user.role=='customer' else None
    if row and row.totp_enabled:
        token=jwt.encode({'sub':str(user.id),'ver':user.token_version,'provider':provider,'jti':secrets.token_hex(16),'exp':now()+timedelta(minutes=5),'aud':'dashvanti-2fa'},settings.jwt_secret,algorithm='HS256')
        return {'two_factor_required':True,'challenge':token}
    audit_login(db,user,provider,request)
    return None

def complete_second_factor(db,data,request=None):
    try:
        claims=jwt.decode(data.challenge,settings.jwt_secret,algorithms=['HS256'],audience='dashvanti-2fa');user=db.get(User,int(claims['sub']))
        if not user or user.role!='customer' or claims['ver']!=user.token_version:raise ValueError()
    except (jwt.PyJWTError,KeyError,ValueError):raise HTTPException(401,'Login verification expired')
    from backend.services.redis_geo_service import client
    try:
        key='account:2fa:'+hashlib.sha256(data.challenge.encode()).hexdigest()
        attempts=client().incr(key);client().expire(key,300)
    except Exception:raise HTTPException(503,'Login verification temporarily unavailable')
    if attempts>5:raise HTTPException(429,'Too many attempts. Sign in again.')
    verify_totp(db,user,data.code);audit_login(db,user,claims['provider'],request)
    from backend.services.session_service import issue_tokens
    return issue_tokens(user)

def stripe_request(method,path,data=None):
    key=os.environ.get('STRIPE_SECRET_KEY')
    if not key:raise HTTPException(503,'Card storage is not configured. Contact support.')
    try:
        response=httpx.request(method,'https://api.stripe.com/v1/'+path,auth=(key,''),data=data,timeout=15)
        if response.is_error:raise HTTPException(502,'Payment provider could not complete this request')
        return response.json()
    except httpx.RequestError:raise HTTPException(503,'Payment provider temporarily unavailable')

def action(db,user,name,data):
    if name=='timezone_detect':
        try:ZoneInfo(str(data['timezone']))
        except ZoneInfoNotFoundError:raise HTTPException(422,'Invalid timezone')
        profile=record(db,CustomerProfile,user)
        if not profile.timezone_detected:profile.timezone=str(data['timezone']);profile.timezone_detected=True
    elif name=='favorite_add':
        uid=int(data['restaurant_id'])
        if not db.get(Restaurant,uid):raise HTTPException(404,'Restaurant not found')
        if not db.get(CustomerFavorite,(user.id,uid)):db.add(CustomerFavorite(customer_id=user.id,restaurant_id=uid))
    elif name=='favorite_remove':
        row=db.get(CustomerFavorite,(user.id,int(data['restaurant_id'])))
        if row:db.delete(row)
    elif name in {'address_save','address_default','address_delete'}:
        from backend.schemas import AddressInput
        from backend.services.user_service import save_address,delete_address
        uid=int(data['id']) if data.get('id') else None
        if name=='address_delete':return delete_address(db,user,uid)
        if name=='address_default':
            row=owned(db,Address,uid,user);db.scalar(select(Customer).where(Customer.id==user.id).with_for_update());db.execute(update(Address).where(Address.customer_id==user.id).values(is_default=False));row.is_default=True
        else:
            row=save_address(db,user,AddressInput(label=str(data['label'])[:80],details=str(data['details'])[:500],is_default=data.get('is_default') is True),uid)
            metadata=db.get(CustomerAddressDetails,row.id)
            if not metadata:metadata=CustomerAddressDetails(address_id=row.id);db.add(metadata)
            if data.get('address_type','Home') not in {'Home','Work','Other'}:raise HTTPException(422,'Invalid address type')
            for field,limit in [('address_type',10),('apartment',100),('landmark',150),('zip_code',20),('instructions',500)]:setattr(metadata,field,str(data.get(field,'Home' if field=='address_type' else ''))[:limit])
            for field in ('country','state','city'):
                if data.get(field):setattr(row,field,str(data[field])[:100])
            for field,limit in [('latitude',90),('longitude',180)]:
                if data.get(field) not in ('',None):
                    value=float(data[field])
                    if not -limit<=value<=limit:raise HTTPException(422,'Invalid coordinates')
                    setattr(row,field,value)
            if (row.latitude is None)!=(row.longitude is None):raise HTTPException(422,'Provide both coordinates')
    elif name=='notifications':
        row=record(db,CustomerNotificationSettings,user)
        for field in NOTIFICATION_FIELDS:
            if not isinstance(data.get(field),bool):raise HTTPException(422,'Invalid notification setting')
            setattr(row,field,data[field])
    elif name=='coupon_save':
        uid=int(data['id']);promotion=db.get(Promotion,uid)
        from backend.services.account_experience_service import promotion_allowed
        if not promotion or not promotion_allowed(db,promotion,user) or not promotion.enabled or promotion.ends_at and promotion.ends_at<=now():raise HTTPException(409,'Coupon unavailable')
        if not db.get(CustomerCoupon,(user.id,uid)):db.add(CustomerCoupon(customer_id=user.id,promotion_id=uid))
    elif name=='redeem':
        db.scalar(select(Customer).where(Customer.id==user.id).with_for_update());points=int(data['points']);available=db.scalar(select(func.coalesce(func.sum(CustomerReward.points),0)).where(CustomerReward.customer_id==user.id))
        rate=Decimal(config(db,'reward_value_'+currency(user)[0]))
        if rate<=0:raise HTTPException(409,'Reward redemption is not enabled yet')
        if points<=0 or points>available:raise HTTPException(409,'Not enough reward points')
        reference='reward:'+secrets.token_hex(16);db.add(CustomerReward(customer_id=user.id,points=-points,description='Redeemed to wallet',reference=reference));wallet_credit(db,user,(rate*points).quantize(Decimal('.01')),'promotion',reference,'Reward points redemption')
    elif name=='support_create':
        from backend.account_enhancement_schemas import TicketInput
        from backend.services.incident_service import create
        return create(db,user,TicketInput(**{key:value for key,value in data.items() if key in {'order_id','category','subcategory','priority','description'} and value!=''}))
    elif name=='support_reply':
        from backend.account_enhancement_schemas import TicketAction
        from backend.services.incident_service import change
        return change(db,user,int(data['id']),TicketAction(action='reply',body=str(data.get('body',''))))
    elif name in {'review_update','review_delete'}:
        row=owned(db,Review,data['id'],user)
        if name=='review_delete':
            db.execute(delete(Rating).where(Rating.order_id==row.order_id));db.delete(row)
        else:
            value=int(data['rating']);driver=int(data['driver_rating']) if data.get('driver_rating') else None
            if not 1<=value<=5 or driver is not None and not 1<=driver<=5:raise HTTPException(422,'Rating must be between 1 and 5')
            if driver is not None and not db.get(Order,row.order_id).driver_id:raise HTTPException(422,'This order has no driver to rate')
            from backend.account_enhancement_models import ReviewPublication
            publication=db.get(ReviewPublication,row.id)
            if not publication:publication=ReviewPublication(review_id=row.id);db.add(publication)
            publication.title=str(data.get('title',''))[:120];publication.status='pending';publication.moderated_at=None
            row.text=str(data.get('text',''))[:2000];rating=db.scalar(select(Rating).where(Rating.order_id==row.order_id))
            if not rating:rating=Rating(order_id=row.order_id);db.add(rating)
            rating.restaurant=value;rating.driver=driver
    elif name=='payment_start':
        from backend.services.account_gateway_service import require
        require(db,user,'stripe')
        profile=record(db,CustomerProfile,user)
        if not profile.stripe_customer_id:profile.stripe_customer_id=stripe_request('POST','customers',{'email':user.email,'name':user.name,'metadata[dashvanti_user_id]':str(user.id)})['id']
        session=stripe_request('POST','checkout/sessions',{'mode':'setup','customer':profile.stripe_customer_id,'currency':currency(user)[0].lower(),'payment_method_types[0]':'card','setup_intent_data[usage]':'on_session','metadata[dashvanti_user_id]':str(user.id),'success_url':'https://customer.dashvanti.com/customer/account/payment-methods?session_id={CHECKOUT_SESSION_ID}','cancel_url':'https://customer.dashvanti.com/customer/account/payment-methods'})
        return {'redirect':session['url']}
    elif name=='payment_complete':
        session=stripe_request('GET','checkout/sessions/'+quote(str(data['session_id']),safe=''))
        profile=record(db,CustomerProfile,user)
        if session.get('customer')!=profile.stripe_customer_id or session.get('metadata',{}).get('dashvanti_user_id')!=str(user.id) or session.get('status')!='complete':raise HTTPException(403,'Payment setup is not complete or belongs to another account')
        setup=stripe_request('GET','setup_intents/'+session['setup_intent'])
        if setup.get('status')!='succeeded':raise HTTPException(409,'Payment setup pending')
        method=stripe_request('GET','payment_methods/'+setup['payment_method']);card=method.get('card')
        if not card:raise HTTPException(422,'A card was not returned')
        if not db.scalar(select(CustomerPaymentMethod.id).where(CustomerPaymentMethod.provider_token==method['id'])):db.add(CustomerPaymentMethod(customer_id=user.id,provider='stripe',provider_customer_id=profile.stripe_customer_id,provider_token=method['id'],brand=card['brand'],last4=card['last4'],exp_month=card['exp_month'],exp_year=card['exp_year'],is_default=not bool(db.scalar(select(CustomerPaymentMethod.id).where(CustomerPaymentMethod.customer_id==user.id)))))
    elif name in {'payment_remove','payment_default'}:
        method=owned(db,CustomerPaymentMethod,data['id'],user)
        if name=='payment_remove':stripe_request('POST','payment_methods/'+method.provider_token+'/detach');db.delete(method)
        else:db.execute(update(CustomerPaymentMethod).where(CustomerPaymentMethod.customer_id==user.id).values(is_default=False));method.is_default=True
    elif name in {'password','logout_all','delete_request','totp_setup','totp_enable','totp_disable'}:
        reauthenticate(user,str(data.get('current_password','')));security=record(db,CustomerSecurity,user)
        if name=='password':
            password=str(data.get('password',''))
            if len(password)<12 or len(password)>128:raise HTTPException(422,'Use a password between 12 and 128 characters')
            from backend.services.auth_service import passwords
            user.password=passwords.hash(password);user.token_version+=1
        elif name=='logout_all':user.token_version+=1
        elif name=='delete_request':
            if data.get('confirm')!='DELETE':raise HTTPException(422,'Type DELETE to confirm')
            security.deletion_requested_at=now();db.add(SupportTicket(user_id=user.id,subject='Account deletion request',description='Customer confirmed deletion of profile, addresses, favorites, wallet information, coupons and order preferences. Process according to retention requirements.'))
        elif name=='totp_setup':
            if security.totp_enabled:raise HTTPException(409,'Disable the existing authenticator before replacing it')
            secret=base64.b32encode(secrets.token_bytes(20)).decode();security.totp_secret=crypt().encrypt(secret.encode()).decode();security.last_totp_step=-1
            return {'message':'Add this key to your authenticator, then enter its six-digit code.','secret':secret,'uri':'otpauth://totp/'+quote('Dashvanti:'+user.email)+'?secret='+secret+'&issuer=Dashvanti'}
        elif name=='totp_enable':verify_totp(db,user,data.get('code',''));security.totp_enabled=True
        elif name=='totp_disable':verify_totp(db,user,data.get('code',''));security.totp_enabled=False;security.totp_secret=None
    elif name=='referral_claim':
        row=record(db,CustomerReferral,user);referrer=db.scalar(select(CustomerReferral).where(CustomerReferral.code==str(data.get('code','')).upper()))
        if not referrer or referrer.customer_id==user.id or row.referred_by:raise HTTPException(409,'Referral code unavailable')
        if db.scalar(select(Order.id).where(Order.customer_id==user.id)):raise HTTPException(409,'Add a referral before your first order')
        row.referred_by=referrer.customer_id
    else:raise HTTPException(422,'Unknown account action')
    db.flush()
    return {'message':'Changes saved'}

def export(db,user):
    result=snapshot(db,user)
    result.pop('card_setup_available',None)
    return result
