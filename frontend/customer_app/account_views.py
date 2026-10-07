import json
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render,redirect
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from common_app.api import call,APIError
from common_app.views import protected

MENU=[('dashboard','Dashboard','⌂'),('profile','Profile','◉'),('addresses','Saved Addresses','⌖'),('orders','Order History','▤'),('favorites','Favorites','♡'),('rewards','Coupons & Rewards','◇'),('wallet','Wallet','$'),('payment-methods','Payment Methods','▣'),('reviews','Reviews & Ratings','★'),('notifications','Notifications','♧'),('support','Support Center','?'),('security','Privacy & Security','♙'),('referral','Referral Program','↗'),('legal','Legal','§')]

from common_app.account_experience import proxy as experience_proxy

@protected
@require_http_methods(['GET','POST'])
def account(request,section='dashboard'):
    if section not in dict((key,title) for key,title,_ in MENU):return HttpResponse(status=404)
    result=None
    fragment=request.headers.get('X-Account-Panel')=='1'
    error=''
    if request.method=='POST':
        name=request.POST.get('action','')
        data=request.POST.dict();data.pop('csrfmiddlewaretoken',None);data.pop('action',None)
        try:
            if name=='profile':
                data['date_of_birth']=data.get('date_of_birth') or None
                result=call(request,'PUT','/customer/account/profile',data)
                request.session['name']=result.get('name',request.session.get('name'));request.session['email']=data['email']
            elif name=='photo':
                file=request.FILES.get('photo')
                if not file:raise APIError('Choose a photo')
                result=call(request,'POST','/files',{'purpose':'profile'},files={'file':(file.name,file,file.content_type)});request.session['profile_photo']=result['id']
            elif name.startswith('experience_'):
                mapping={
                    'experience_favorite':('favorites',None),
                    'experience_wallet_add':('wallet/funding',None),
                    'experience_wallet_transfer':('wallet/transfer',None),
                    'experience_review':('reviews',None),
                }
                endpoint,payload=mapping[name]
                if name=='experience_favorite':
                    payload={'kind':data['kind'],'target_id':int(data['target_id']),'enabled':data.get('enabled')=='true'}
                elif payload is None:
                    fields={'experience_wallet_add':('amount','gateway','request_key'),'experience_wallet_transfer':('recipient_email','amount','request_key','current_password'),'experience_review':('order_id','rating','title','comment')}[name]
                    payload={key:data.get(key,'') for key in fields}
                result=call(request,'POST','/account-experience/'+endpoint,payload)
                if name=='experience_review' and request.FILES.get('review_photo'):
                    file=request.FILES['review_photo'];call(request,'POST','/files',{'purpose':'review','entity_id':result['id']},files={'file':(file.name,file,file.content_type)})
            else:
                if name=='notifications':data={key:key in request.POST for key in ['order_updates','delivery_alerts','sms','email','push','promotions','referral_rewards','system_alerts']}
                if name=='address_save':data['is_default']='is_default' in request.POST
                result=call(request,'POST','/customer/account/action',{'action':name,'data':data})
                if name=='timezone_detect':return JsonResponse(result)
                if result.get('redirect'):
                    return JsonResponse({'redirect':result['redirect']}) if fragment else redirect(result['redirect'])
                if name in {'logout_all','password'}:
                    request.session.flush();messages.success(request,'Security updated. Sign in again.')
                    return JsonResponse({'redirect':'/customer/login'}) if fragment else redirect('/customer/login')
            if result and result.get('redirect'):
                return JsonResponse({'redirect':result['redirect']}) if fragment else redirect(result['redirect'])
            if not fragment:
                messages.success(request,result.get('message','Changes saved'))
                if not (result and result.get('secret')):return redirect(request.path)
        except (APIError,KeyError,ValueError) as exc:
            error=str(exc) if isinstance(exc,APIError) else 'Check the required fields'
            if not fragment:messages.error(request,error)
    if section=='payment-methods' and request.GET.get('session_id'):
        try:call(request,'POST','/customer/account/action',{'action':'payment_complete','data':{'session_id':request.GET['session_id']}});messages.success(request,'Payment method saved')
        except APIError as exc:messages.error(request,str(exc))
        return redirect('/customer/account/payment-methods')
    if section=='wallet' and request.GET.get('funding_id'):
        try:result=call(request,'POST','/account-experience/wallet/funding/'+request.GET['funding_id']+'/verify',{})
        except APIError as exc:error=str(exc)
    data=call(request,'GET','/customer/account')
    if data.get('avatar','').startswith('/api/account-experience/'):
        data['avatar']='/customer/experience/'+data['avatar'].removeprefix('/api/account-experience/')
    context={'account':data,'account_menu':MENU,'section':section,'title':dict((key,title) for key,title,_ in MENU)[section],'totp_setup':result if result and result.get('secret') else None,'notification_options':[(key,key.replace('_',' ').title(),value) for key,value in data['notifications'].items()], 'account_error':error,'account_message':result.get('message','Changes saved') if result and not error else '', 'funding_id':request.GET.get('funding_id',''), 'funding_pending':bool(result and result.get('status')=='pending')}
    if section=='support':
        filters={key:value for key,value in request.GET.items() if key in {'q','status','priority','category','date_from','date_to','sort','direction','page','size'} and value}
        context['incidents']=call(request,'GET','/account-experience/tickets',params=filters)
        context['ticket_filters']=filters
        context['ticket_statuses']=['Open','Assigned','In Progress','Waiting Customer','Escalated','Resolved','Closed']
        context['tickets_has_next']=context['incidents']['page']*context['incidents']['size']<context['incidents']['total']
    if fragment:
        return JsonResponse({'html':render_to_string('customer_app/account_panel.html',context,request=request),'avatar':data.get('avatar',''),'name':data['user']['name'],'theme':data['profile']['theme'],'error':error},status=422 if error else 200)
    return render(request,'customer_app/account.html',context)

@protected
def export(request):
    result=call(request,'GET','/customer/account/export',raw=True)
    response=HttpResponse(result.content,content_type='application/json');response['Content-Disposition']='attachment; filename="dashvanti-account.json"';response['Cache-Control']='no-store';return response

@require_http_methods(['GET','POST'])
def verify_login(request):
    if not request.session.get('account_2fa_challenge'):return redirect('/customer/login')
    error=''
    if request.method=='POST':
        try:
            result=call(request,'POST','/auth/account-2fa',{'challenge':request.session['account_2fa_challenge'],'code':request.POST.get('code','')})
            provider=request.session.get('account_2fa_provider','email');request.session.flush();request.session.update({'token':result['access_token'],'refresh_token':result['refresh_token'],'role':'customer','auth_provider':provider})
            user=call(request,'GET','/me');request.session.update({'name':user['name'],'email':user['email'],'user_id':user['id'],'profile_photo':user['profile_photo'],'order_mode':user.get('order_mode') or 'delivery'})
            return redirect('/customer/dashboard')
        except APIError as exc:error=str(exc)
    return render(request,'customer_app/account_verify.html',{'error':error})

def admin_account(request,customer_id):
    if request.session.get('role')!='admin' or not request.session.get('token'):return HttpResponseForbidden()
    section=request.GET.get('section','dashboard')
    if section not in dict((key,title) for key,title,_ in MENU):section='dashboard'
    data=call(request,'GET',f'/admin/customers/{customer_id}/account')
    if data.get('avatar','').startswith('/api/account-experience/'):
        data['avatar']='/admin/experience/'+data['avatar'].removeprefix('/api/account-experience/')
    context={'account':data,'account_menu':MENU,'section':section,'title':'Customer account','read_only':True,'notification_options':[(key,key.replace('_',' ').title(),value) for key,value in data['notifications'].items()]}
    if section=='support':
        filters={key:value for key,value in request.GET.items() if key in {'q','status','priority','category','date_from','date_to','sort','direction','page','size'} and value}
        context['incidents']=call(request,'GET','/account-experience/tickets',params={**filters,'customer_id':customer_id})
        context.update(ticket_filters=filters,ticket_statuses=['Open','Assigned','In Progress','Waiting Customer','Escalated','Resolved','Closed'],tickets_has_next=context['incidents']['page']*context['incidents']['size']<context['incidents']['total'])
    if request.headers.get('X-Account-Panel')=='1':
        return JsonResponse({'html':render_to_string('customer_app/account_panel.html',context,request=request)})
    return render(request,'customer_app/account.html',context)
