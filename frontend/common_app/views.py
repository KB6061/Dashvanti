from django.conf import settings
from functools import wraps
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from common_app.api import call, APIError
from common_app.forms import LoginForm, RegisterForm, ForgotForm, ResetForm, ProfileForm, UploadForm

def protected(view):
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        portal = request.path.strip('/').split('/')[0]
        if not request.session.get('token') or request.session.get('role') != portal:
            if request.path == '/customer/restaurants':
                request.session['customer_browse_path'] = request.get_full_path()
            return redirect('/'+portal+'/login')
        try:
            if portal == 'driver' and (request.path == '/driver/files' or request.path.startswith('/driver/files/')):
                from driver_app.agreement_views import consent_status
                if not consent_status(request).get('accepted'): return redirect('/driver/agreement')
            return view(request,*args,**kwargs)
        except APIError as exc:
            if exc.status == 401:
                request.session.flush()
                return redirect('/'+portal+'/login')
            return render(request,'error.html',{'error':str(exc)},status=exc.status)
    return wrapped

@require_http_methods(['GET','POST'])
def auth(request, role, action):
    if role == 'customer' and action == 'register' and request.GET.get('ref'):
        request.session['pending_referral'] = request.GET['ref'][:32]

    if request.method == 'GET' and action in {'login', 'register'} and request.session.get('token') and request.session.get('role') == role:
        try:
            call(request, 'GET', '/me')
        except APIError as exc:
            if exc.status == 401:
                request.session.flush()
            else:
                return render(request, 'error.html', {'error': str(exc)}, status=exc.status)
        else:
            return redirect('/' + role + '/dashboard')
    agreement = None
    if role == 'driver' and action == 'register':
        from driver_app.agreement_views import consent_status
        try:
            agreement = consent_status(request)
        except APIError as exc:
            return render(request, 'error.html', {'error': str(exc)}, status=exc.status)
        if not agreement.get('accepted'):
            return redirect('/driver/agreement')
    cls = {'login':LoginForm,'register':RegisterForm,'forgot':ForgotForm,'reset':ResetForm}[action]
    initial = {'token':request.GET.get('token','')}
    if agreement: initial['name'] = agreement['full_legal_name']
    form = cls(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        if action in {'login','register'}:
            data['role'] = role
        if role == 'customer' and action == 'register':
            data['referral_code'] = request.session.get('pending_referral')
        if role == 'driver' and action == 'register':
            data['driver_agreement_token'] = request.session.get('driver_agreement_token')
        try:
            result = call(request,'POST','/auth/'+action,data)
            if action == 'login':
                if result.get('two_factor_required'):
                    request.session['account_2fa_challenge'] = result['challenge']
                    request.session['account_2fa_provider'] = 'email'
                    return redirect('/customer/account/verify-login')
                request.session.pop('social_login', None)
                request.session.pop('auth_provider', None)
                request.session.cycle_key()
                request.session['token'] = result['access_token']
                if result.get('refresh_token'):
                    request.session['refresh_token'] = result['refresh_token']
                request.session['role'] = role
                try:
                    me = call(request,'GET','/me')
                    request.session['name'] = me.get('name','')
                    request.session['email'] = me.get('email','')
                    request.session['user_id'] = me.get('id')
                    request.session['order_mode'] = me.get('order_mode') or 'delivery'
                    request.session['profile_photo'] = me.get('profile_photo')
                except APIError:
                    request.session['name'] = ''
                    request.session['email'] = ''
                    request.session['order_mode'] = 'delivery'
                    request.session['profile_photo'] = None
                if role == 'customer':
                    request.session.pop('customer_browse_path', None)
                    return redirect('/customer/dashboard')
                return redirect('/'+role+'/dashboard')
            if role == 'driver' and action == 'register':
                from driver_app.agreement_views import clear_consent
                clear_consent(request)
            messages.success(request,result.get('message','Account created. Please sign in.'))
            return redirect('/'+role+'/login')
        except APIError as exc:
            form.add_error(None,str(exc))
    labels = {'login':'Login','register':'Create account','forgot':'Send reset link','reset':'Reset password'}
    titles = {'login':'Welcome back','register':'Create your Dashvanti account','forgot':'Recover access','reset':'Choose a new password'}
    welcome = {
        'restaurant': ('Your kitchen. More customers.', 'Serve great food. Grow with Dashvanti.', 'Manage your menu, receive orders, and bring your food to more people.'),
        'driver': ('Your time. Your journey.', 'Deliver smiles. Earn on your schedule.', 'Find delivery opportunities, manage your orders, and track your earnings.')
    }.get(role, ('', '', ''))
    login_form = form if action == 'login' else LoginForm()
    register_form = form if action == 'register' else RegisterForm()
    login_form.auto_id = 'login_%s'
    register_form.auto_id = 'register_%s'
    return render(request,role+'_app/auth.html',{'form':form,'title':titles[action],'submit_label':labels[action],'auth_action':action,
        'welcome_eyebrow': welcome[0], 'welcome_title': welcome[1], 'welcome_description': welcome[2],
        'customer_login_form': login_form,
        'customer_register_form': register_form,
        'customer_login_method': 'mobile' if request.POST.get('login_method') == 'mobile' else 'email',
        'driver_registration_allowed': role != 'driver' or action == 'register',
        'open_auth': action})

@require_http_methods(['POST'])
def logout(request,role):
    try:
        call(request,'POST','/auth/logout')
    except APIError:
        pass
    request.session.flush()
    response=redirect('/'+role+'/login')
    response['Cache-Control']='no-store'
    response['Clear-Site-Data']='"cache", "cookies", "storage"'
    return response

@protected
@require_http_methods(['GET','POST'])
def profile(request):
    me = call(request,'GET','/me')
    form = ProfileForm(request.POST or None,initial=me)
    if request.method=='POST' and form.is_valid():
        call(request,'PUT','/me',form.cleaned_data)
        photo=request.FILES.get('profile_photo')
        if photo:
            uploaded=call(request,'POST','/files',{'purpose':'profile'},files={'file':(photo.name,photo,photo.content_type)})
            request.session['profile_photo']=uploaded.get('id')
        request.session['name'] = form.cleaned_data.get('name','')
        request.session['email'] = form.cleaned_data.get('email','')
        messages.success(request,'Profile saved')
        return redirect(request.path)
    return render(request,'account_components/portal_profile.html',{'form':form,'title':'Your profile','identity':call(request,'GET','/account-experience/identity')})

@protected
@require_http_methods(['GET','POST'])
def files(request):
    form = UploadForm(request.POST or None,request.FILES or None,role=request.session['role'])
    if request.method=='POST' and form.is_valid():
        data = dict(form.cleaned_data)
        upload = data.pop('file')
        if data['entity_id'] is None:
            data.pop('entity_id')
        call(request,'POST','/files',data,files={'file':(upload.name,upload,upload.content_type)})
        messages.success(request,'File uploaded')
        return redirect(request.path)
    return render(request,'files.html',{'form':form,'files':call(request,'GET','/files'),'title':'Photos & documents'})

@protected
@require_http_methods(['GET'])
def download(request,file_id):
    thumbnail = request.GET.get('size') == 'menu'
    response = call(request,'GET',f'/files/{file_id}' + ('/thumbnail' if thumbnail else ''),raw=True)
    return HttpResponse(response.content,content_type=response.headers.get('content-type','image/jpeg'),headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=' + ('86400' if thumbnail else '300')})

@protected
@require_http_methods(['GET'])
def orders(request):
    role = request.session['role']
    return render(request,role+'_app/orders.html',{'orders':call(request,'GET','/orders'),'title':'Orders'})

@protected
@require_http_methods(['GET','POST'])
def order(request,order_id):
    role = request.session['role']
    if request.method=='POST':
        if role == 'driver' and request.POST.get('otp'):
            updated=call(request,'POST',f'/orders/{order_id}/delivery-otp',{'otp':request.POST['otp']})
        else:
            updated=call(request,'POST','/order/update',{'order_id':order_id,'status':request.POST.get('status','')})
        if role=='driver' and request.POST.get('status')=='DELIVERED':
            upcoming=next((row for row in call(request,'GET','/orders') if row['status'] not in {'DELIVERED','CANCELLED','CANCELED','REJECTED'}),None)
            if upcoming:
                url=f"/driver/order/{upcoming['id']}"
                if request.headers.get('X-Requested-With')=='XMLHttpRequest':return JsonResponse({'redirect_url':url})
                return redirect(url)
        if request.headers.get('X-Requested-With')=='XMLHttpRequest':return JsonResponse({'live_order_update':True,'order_id':order_id,'status':updated['status']})
        return redirect(request.path)
    result = call(request,'GET',f'/orders/{order_id}')
    if result['order']['status']=='CANCELLED':
        result['cancellation']=call(request,'GET',f'/orders/{order_id}/cancellation')
    if role == 'customer':
        result['delivery_otp'] = call(request, 'GET', f'/orders/{order_id}/delivery-otp').get('otp')
        try:
            result['driver_location'] = call(request,'GET',f'/order/{order_id}/driver/location')
        except APIError:
            result['driver_location'] = None
        restaurant_data = result.get('restaurant') or {}
        order_data = result.get('order') or {}
        markers = []
        if restaurant_data.get('address'):
            markers.append({
                'id': 'restaurant',
                'type': 'restaurant',
                'name': restaurant_data.get('name') or 'Restaurant',
                'address': restaurant_data['address'],
            })
        if order_data.get('mode') == 'delivery' and order_data.get('address'):
            markers.append({
                'id': 'destination',
                'type': 'destination',
                'name': 'Delivery address',
                'address': order_data['address'],
            })
        if result['driver_location']:
            markers.append({
                'id': 'driver',
                'type': 'driver',
                'name': (result.get('driver') or {}).get('name') or 'Delivery partner',
                'latitude': result['driver_location']['latitude'],
                'longitude': result['driver_location']['longitude'],
            })
        result['tracking_markers'] = markers
    if request.GET.get('poll') == '1':
        return JsonResponse(result,headers={'Cache-Control':'no-store'})
    # UI choices are advisory; the API enforces every transition under a row lock.
    transitions = {'restaurant':{'PLACED':['ACCEPTED','REJECTED'],'ACCEPTED':['PREPARING'],'CONFIRMED':['PREPARING'],'PREPARING':['READY_FOR_PICKUP']},'driver':{'READY_FOR_PICKUP':['ON_THE_WAY_TO_RESTAURANT'],'ON_THE_WAY_TO_RESTAURANT':['PICKED_UP'],'PICKED_UP':['ON_THE_WAY_TO_CUSTOMER'],'ON_THE_WAY_TO_CUSTOMER':['DELIVERED']}}
    transitions['restaurant'].update({'PREPARING':['PACKING','READY_FOR_PICKUP'],'PACKING':['WRAPPING_UP','READY_FOR_PICKUP'],'WRAPPING_UP':['READY_FOR_PICKUP']})
    transitions['driver'].update({'DRIVER_ASSIGNED':['ON_THE_WAY_TO_RESTAURANT'],'ON_THE_WAY_TO_RESTAURANT':['ARRIVED_AT_RESTAURANT'],'ARRIVED_AT_RESTAURANT':['PICKED_UP']})
    action_status = result['order']['status']
    if role == 'driver':
        result['requires_delivery_otp'] = call(request, 'GET', f'/orders/{order_id}/delivery-verification')['required']
        activity = call(request, 'GET', f'/order/{order_id}/tracking')
        action_status = activity['driver_status']
        if action_status == 'ARRIVED_AT_RESTAURANT' and activity['restaurant_status'] != 'READY_FOR_PICKUP':
            action_status = None
    result['actions'] = transitions.get(role,{}).get(action_status,[])
    if role=='restaurant' and result['order']['mode']=='pickup' and result['order']['status']=='READY_FOR_PICKUP':
        result['actions'] = ['DELIVERED']
    result['show_live_map'] = request.GET.get('history') != '1' and result['order']['status'] not in {'DELIVERED', 'CANCELLED', 'CANCELED', 'REJECTED'}
    return render(request,role+'_app/order.html',result)

@protected
@require_http_methods(['GET'])
def stats(request):
    return render(request,'stats.html',call(request,'GET','/stats',params={'period':request.GET.get('period','daily')}))


@protected
@require_http_methods(['GET', 'POST'])
def support(request):
    if request.session.get('role')=='customer':return redirect('/customer/account/support')
    from django.template.loader import render_to_string
    from django.http import JsonResponse
    filters={key:value for key,value in request.GET.items() if key in {'q','status','priority','category','date_from','date_to','sort','direction','page','size'} and value}
    result=call(request,'GET','/account-experience/tickets',params=filters)
    context={'incidents':result,'ticket_filters':filters,'orders':call(request,'GET','/orders'),'title':'Support Center','ticket_statuses':['Open','Assigned','In Progress','Waiting Customer','Escalated','Resolved','Closed'],'tickets_has_next':result['page']*result['size']<result['total']}
    if request.headers.get('X-Incident-Panel')=='1':return JsonResponse({'html':render_to_string('account_components/ticket_list.html',context,request=request)})
    return render(request,'account_components/support_page.html',context)

@protected
@require_http_methods(['GET', 'POST'])
def chat(request, order_id):
    if request.method == 'POST':
        call(request, 'POST', f'/operations/orders/{order_id}/messages', {'body': request.POST.get('body', '')})
        return redirect(request.path)
    return render(request, 'operations.html', {
        'mode': 'chat', 'messages': call(request, 'GET', f'/operations/orders/{order_id}/messages'),
        'order_id': order_id, 'title': f'Order -{order_id} messages',
    })

@protected
@require_http_methods(['GET', 'POST'])
def notifications(request):
    if request.method == 'POST':
        call(request, 'POST', f"/operations/notifications/{request.POST.get('notification_id')}/read")
        return redirect(request.path)
    return render(request, 'operations.html', {
        'mode': 'notifications', 'notifications': call(request, 'GET', '/operations/notifications'),
        'title': 'Updates',
    })

@protected
@require_http_methods(['GET'])
def live_alerts(request):
    role = request.session['role']
    if request.GET.get('messages') == '1':
        return JsonResponse(call(request, 'GET', '/operations/notifications'), safe=False)
    if request.GET.get('statuses') == '1':
        return JsonResponse(call(request, 'GET', '/orders'), safe=False)
    if role == 'customer':
        return JsonResponse([], safe=False)
    if role == 'driver':
        return JsonResponse(call(request, 'GET', '/delivery/available'), safe=False)
    rows = call(request, 'GET', '/orders')
    return JsonResponse([row for row in rows if row['status'] == 'PLACED'], safe=False)

@protected
@require_http_methods(['GET'])
def download_report(request, order_id=None):
    path = f'/reports/orders/{order_id}/bill' if order_id is not None else '/reports/earnings'
    result = call(request, 'GET', path, params={'period': request.GET.get('period', 'monthly'), 'tz': request.GET.get('tz', 'America/Chicago')}, raw=True)
    if request.GET.get('format') not in {'inline', 'download'}:
        from urllib.parse import urlencode
        query = {'period': request.GET.get('period', 'monthly')}
        response = render(request, 'report_viewer.html', {
            'title': f'Order -{order_id} bill' if order_id is not None else 'Earnings report',
            'pdf_url': request.path + '?' + urlencode({**query, 'format': 'inline'}),
            'download_url': request.path + '?' + urlencode({**query, 'format': 'download'}),
        })
    else:
        response = HttpResponse(result.content, content_type='application/pdf')
        disposition = result.headers['Content-Disposition']
        response['Content-Disposition'] = disposition.replace('attachment;', 'inline;', 1) if request.GET['format'] == 'inline' else disposition
        response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Cache-Control'] = 'private, no-store'
    return response

@protected
@require_http_methods(['POST'])
def route_distance(request):
    import json
    try:
        data = json.loads(request.body)
        return JsonResponse(call(request, 'POST', '/routes/distance', data))
    except (ValueError, TypeError):
        return JsonResponse({'detail': 'Invalid route coordinates'}, status=400)
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)

@protected
@require_http_methods(['GET', 'POST'])
def order_sound(request):
    try:
        if request.method == 'POST':
            return JsonResponse(call(request, 'PUT', '/me/order-sound', {'enabled': request.POST.get('enabled') == 'true'}))
        return JsonResponse(call(request, 'GET', '/me/order-sound'))
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)

@protected
@require_http_methods(['GET'])
def tracking(request, order_id):
    return JsonResponse(call(request, 'GET', f'/order/{order_id}/tracking'), headers={'Cache-Control':'no-store'})

@protected
@require_http_methods(['GET','POST'])
def cancellation(request, order_id):
    try:
        if request.method == 'GET':
            result=call(request,'GET',f'/orders/{order_id}/cancellation')
        else:
            import json
            result=call(request,'POST',f'/orders/{order_id}/cancellation',json.loads(request.body))
        return JsonResponse(result,headers={'Cache-Control':'no-store'})
    except APIError as exc:
        return JsonResponse({'detail':str(exc)},status=exc.status)
    except ValueError:
        return JsonResponse({'detail':'Invalid request'},status=400)


@require_http_methods(['GET'])
def navigation_state(request):
    portal = request.path.strip('/').split('/')[0]
    if portal == 'admin':
        if not request.session.get('admin_authenticated'):
            return JsonResponse({'detail': 'Sign in required'}, status=401)
        from admin_app.views import admin_api
        result = admin_api('GET', '/operations/admin/navigation-state')
    else:
        if not request.session.get('token') or request.session.get('role') != portal:
            return JsonResponse({'detail': 'Sign in required'}, status=401)
        result = call(request, 'GET', '/operations/navigation-state')
    return JsonResponse(result, headers={'Cache-Control': 'no-store'})

@require_http_methods(['GET'])
def about_us(request):
    portal = settings.PORTAL_ROLE or 'customer'
    return render(request, 'about_us.html', {'portal': portal, 'signed_in': bool(request.session.get('token')) and request.session.get('role') == portal, 'about_base': 'landing-base.html' if portal == 'main' else 'base.html', 'founder_photo': '/static/krishna-founder.webp?v=2' if (settings.BASE_DIR / 'static' / 'krishna-founder.webp').is_file() else None})

@require_http_methods(['POST'])
def gps_ticket(request,portal):
    try:
        if portal=='admin':
            if not request.session.get('admin_authenticated'):return JsonResponse({'detail':'Sign in required'},status=401)
            from admin_app.views import admin_api
            result=admin_api('POST','/gps/admin-ticket')
        else:
            if not request.session.get('token') or request.session.get('role')!=portal:return JsonResponse({'detail':'Sign in required'},status=401)
            order_id=request.GET.get('order_id')
            result=call(request,'POST','/gps/ticket',params={'order_id':int(order_id)} if order_id else None)
        return JsonResponse(result,headers={'Cache-Control':'private, no-store'})
    except APIError as exc:return JsonResponse({'detail':str(exc)},status=exc.status)
    except (RuntimeError,ValueError):return JsonResponse({'detail':'GPS streaming unavailable'},status=503)
