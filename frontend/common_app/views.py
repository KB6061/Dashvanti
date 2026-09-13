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
            return redirect('/'+portal+'/login')
        try:
            return view(request,*args,**kwargs)
        except APIError as exc:
            if exc.status == 401:
                request.session.flush()
                return redirect('/'+portal+'/login')
            return render(request,'error.html',{'error':str(exc)},status=exc.status)
    return wrapped

@require_http_methods(['GET','POST'])
def auth(request, role, action):
    cls = {'login':LoginForm,'register':RegisterForm,'forgot':ForgotForm,'reset':ResetForm}[action]
    form = cls(request.POST or None,initial={'token':request.GET.get('token','')})
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        if action in {'login','register'}:
            data['role'] = role
        try:
            result = call(request,'POST','/auth/'+action,data)
            if action == 'login':
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
                return redirect('/'+role+('/restaurants' if role=='customer' else '/dashboard'))
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
        'open_auth': action if request.method == 'POST' else ''})

@require_http_methods(['POST'])
def logout(request,role):
    try:
        call(request,'POST','/auth/logout')
    except APIError:
        pass
    request.session.flush()
    return redirect('/'+role+'/login')

@protected
@require_http_methods(['GET','POST'])
def profile(request):
    me = call(request,'GET','/me')
    form = ProfileForm(request.POST or None,initial=me)
    if request.method=='POST' and form.is_valid():
        call(request,'PUT','/me',form.cleaned_data)
        request.session['name'] = form.cleaned_data.get('name','')
        request.session['email'] = form.cleaned_data.get('email','')
        messages.success(request,'Profile saved')
        return redirect(request.path)
    return render(request,'form.html',{'form':form,'title':'Your profile'})

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
        call(request,'POST',f'/orders/{order_id}/status',{'status':request.POST.get('status','')})
        return redirect(request.path)
    result = call(request,'GET',f'/orders/{order_id}')
    if result['order']['status']=='CANCELLED':
        result['cancellation']=call(request,'GET',f'/orders/{order_id}/cancellation')
    if role == 'customer':
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
        activity = call(request, 'GET', f'/order/{order_id}/tracking')
        action_status = activity['driver_status']
        if action_status == 'ARRIVED_AT_RESTAURANT' and activity['restaurant_status'] != 'READY_FOR_PICKUP':
            action_status = None
    result['actions'] = transitions.get(role,{}).get(action_status,[])
    if role=='restaurant' and result['order']['mode']=='pickup' and result['order']['status']=='READY_FOR_PICKUP':
        result['actions'] = ['DELIVERED']
    return render(request,role+'_app/order.html',result)

@protected
@require_http_methods(['GET'])
def stats(request):
    return render(request,'stats.html',call(request,'GET','/stats',params={'period':request.GET.get('period','daily')}))


@protected
@require_http_methods(['GET', 'POST'])
def support(request):
    order_rows = call(request, 'GET', '/orders')
    if request.method == 'POST':
        order_id = request.POST.get('order_id') or None
        payload = {
            'order_id': int(order_id) if order_id else None,
            'subject': request.POST.get('subject', ''),
            'description': request.POST.get('description', ''),
        }
        call(request, 'POST', '/operations/tickets', payload)
        messages.success(request, 'Support ticket created')
        return redirect(request.path)
    return render(request, 'operations.html', {
        'mode': 'support', 'tickets': call(request, 'GET', '/operations/tickets'),
        'orders': order_rows, 'title': 'Support',
    })

@protected
@require_http_methods(['GET', 'POST'])
def chat(request, order_id):
    if request.method == 'POST':
        call(request, 'POST', f'/operations/orders/{order_id}/messages', {'body': request.POST.get('body', '')})
        return redirect(request.path)
    return render(request, 'operations.html', {
        'mode': 'chat', 'messages': call(request, 'GET', f'/operations/orders/{order_id}/messages'),
        'order_id': order_id, 'title': f'Order #{order_id} messages',
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
            'title': f'Order #{order_id} bill' if order_id is not None else 'Earnings report',
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
