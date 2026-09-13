from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from common_app.api import call
from common_app.views import protected, orders, order, stats
from restaurant_app.forms import RestaurantForm, MenuForm

LANES = [
    ('New', ['PLACED', 'ACCEPTED', 'CONFIRMED']),
    ('In Prep', ['PREPARING','PACKING','WRAPPING_UP']),
    ('Ready for Pickup', ['READY_FOR_PICKUP']),
    ('Dispatched', ['DRIVER_ASSIGNED', 'ON_THE_WAY_TO_RESTAURANT', 'PICKED_UP', 'ON_THE_WAY_TO_CUSTOMER', 'DELIVERED']),
]

NEXT_ACTIONS = {
    'PLACED': [('ACCEPTED', 'Accept'), ('REJECTED', 'Reject')],
    'ACCEPTED': [('PREPARING', 'Start Prep')],
    'CONFIRMED': [('PREPARING', 'Start Prep')],
    'PREPARING': [('PACKING', 'Packing'), ('READY_FOR_PICKUP', 'Mark Ready')],
    'PACKING': [('WRAPPING_UP', 'Wrapping up')],
    'WRAPPING_UP': [('READY_FOR_PICKUP', 'Mark Ready')],
    'READY_FOR_PICKUP': [('DELIVERED', 'Complete Pickup')],
}

@protected
@require_http_methods(['GET','POST'])
def dashboard(request):
    if request.method == 'POST' and request.POST.get('dashboard_action') == 'availability':
        call(request,'POST','/restaurant/availability/toggle',{'is_open': request.POST.get('is_open') == 'on'})
        return redirect(request.path)
    if request.method == 'POST' and request.POST.get('dashboard_action') == 'hours':
        call(request,'POST','/restaurant/hours/update',{'opening': request.POST.get('opening','09:00'), 'closing': request.POST.get('closing','22:00')})
        return redirect(request.path)
    profile = call(request,'GET','/me')['restaurant']
    orders = call(request,'GET','/orders')
    menu_items = call(request,'GET','/menu')
    stats_data = call(request,'GET','/stats',params={'period':'daily'})
    lane_cards = []
    for title, statuses in LANES:
        rows = []
        for row in orders:
            if row['status'] in statuses:
                row = dict(row)
                row['actions'] = NEXT_ACTIONS.get(row['status'], [])
                if row['status'] == 'READY_FOR_PICKUP' and row.get('mode') != 'pickup':
                    row['actions'] = []
                rows.append(row)
        lane_cards.append({'title': title, 'orders': rows[:5]})
    visible_items = [item for item in menu_items if item.get('available')]
    top_items = stats_data.get('top_items') or [{'name': item['name'], 'units': ''} for item in visible_items[:4]]
    chart_points = [42, 76, 61, 124, 88, 132, 95]
    context = {
        'profile': profile,
        'orders': orders,
        'incoming_orders': [row for row in orders if row.get('status') == 'PLACED'][:3],
        'menu_items': menu_items[:6],
        'lane_cards': lane_cards,
        'stats': stats_data,
        'top_items': top_items[:4],
        'chart_points': chart_points,
        'new_orders': sum(1 for row in orders if row['status'] in ['PLACED','ACCEPTED','CONFIRMED']),
        'prep_time': profile.get('delivery_minutes') or 18,
        'title':'Restaurant dashboard',
    }
    return render(request,'restaurant_app/dashboard.html',context)

@protected
@require_http_methods(['GET','POST'])
def profile(request):
    me = call(request,'GET','/me')
    restaurant = me['restaurant'] or {}
    form = RestaurantForm(request.POST or None,initial=restaurant)
    if request.method == 'POST' and form.is_valid():
        call(request,'PUT','/restaurant/profile',form.cleaned_data)
        messages.success(request,'Restaurant profile saved')
        return redirect('/restaurant/profile')
    return render(request,'form.html',{'form':form,'title':'Restaurant settings'})

@protected
@require_http_methods(['GET','POST'])
def menu(request,item_id=None):
    rows = call(request,'GET','/menu')
    query = request.GET.get('q','').strip().lower()
    if query:
        rows = [r for r in rows if query in r.get('name','').lower() or query in r.get('description','').lower()]
    current = next((r for r in rows if r['id']==item_id),{})
    form = MenuForm(request.POST or None,request.FILES or None,initial=current)
    if request.method=='POST':
        if request.POST.get('delete') and item_id:
            call(request,'DELETE',f'/menu/{item_id}')
            return redirect('/restaurant/menu')
        if form.is_valid():
            data = dict(form.cleaned_data)
            upload = data.pop('photo',None)
            data['price'] = str(data['price'])
            result = call(request,'PUT' if item_id else 'POST',f'/menu/{item_id}' if item_id else '/menu',data)
            if upload:
                call(request,'POST','/files',{'purpose':'menu','entity_id':result['id']},files={'file':(upload.name,upload,upload.content_type)})
            return redirect('/restaurant/menu')
    return render(request,'restaurant_app/menu.html',{'form':form,'items':rows,'editing':bool(item_id),'title':'Manage menu'})


@protected
@require_http_methods(['GET', 'POST'])
def content(request):
    me = call(request, 'GET', '/me')
    current = call(request, 'GET', '/content/restaurant')
    if request.method == 'POST':
        def upload(name, purpose):
            upload_file = request.FILES.get(name)
            if not upload_file:
                return None
            return call(request, 'POST', '/files', {'purpose': purpose, 'entity_id': me['id']},
                        files={'file': (upload_file.name, upload_file, upload_file.content_type)})['id']

        cover_id = upload('cover', 'cover') or current.get('cover_file_id')
        logo_id = upload('logo', 'logo') or current.get('logo_file_id')
        gallery = [file_id for file_id in current.get('gallery_file_ids', []) if str(file_id) not in request.POST.getlist('remove_gallery')]
        for upload_file in request.FILES.getlist('gallery'):
            gallery.append(call(request, 'POST', '/files', {'purpose': 'gallery', 'entity_id': me['id']},
                                files={'file': (upload_file.name, upload_file, upload_file.content_type)})['id'])
        payload = {
            'cover_file_id': cover_id, 'logo_file_id': logo_id, 'gallery_file_ids': gallery,
            'busy_mode': request.POST.get('busy_mode', current.get('busy_mode', 'open')),
            'busy_until': request.POST.get('busy_until') or None,
            'prep_extra_minutes': request.POST.get('prep_extra_minutes', 0),
            'capacity': request.POST.get('capacity', 20),
        }
        call(request, 'PUT', '/content/restaurant', payload)
        messages.success(request, 'Restaurant content and operations saved')
        return redirect(request.path)
    return render(request, 'restaurant_app/content.html', {'content': current, 'title': 'Brand & operations'})
