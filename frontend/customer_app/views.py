import uuid
from django.contrib import messages
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from common_app.api import call, APIError
from common_app.views import protected, orders, order
from customer_app.forms import AddressForm, CheckoutForm, ReviewForm

@protected
def restaurants(request):
    if request.GET.get('mode') in {'delivery','pickup'}:
        request.session['order_mode'] = request.GET['mode']
    order_mode = request.session.get('order_mode','delivery')
    params = {k:v for k,v in request.GET.items() if v and k in {'q','cuisine','veg','rating','delivery_time','page','page_size'}}
    params.setdefault('page_size', 100)
    cart_data = {'items': [], 'subtotal': 0, 'delivery_fee': 0, 'total': 0}
    cart_count = 0
    try:
        cart_data = call(request,'GET','/cart')
        cart_count = sum(item['quantity'] for item in cart_data.get('items',[]))
    except Exception:
        cart_count = 0
    categories = ['Meal Box','Pizza','Chinese','Fast Food','Mexican','Healthy','Chicken','Burgers','Desserts','Thai','Italian','Indian','Breakfast','Coffee','Salads','Sushi']
    browse = call(request,'GET','/restaurants',params=params)
    restaurants = browse.get('items', browse) if isinstance(browse, dict) else browse
    meta = browse.get('meta', {}) if isinstance(browse, dict) else {}
    orders_data = call(request,'GET','/orders')
    active_order = next((row for row in orders_data if row.get('status') not in {'DELIVERED','REJECTED','CANCELLED','CANCELED'}), None)
    featured = []
    for restaurant_row in restaurants:
        for item in restaurant_row.get('matches', []):
            item = dict(item)
            item['restaurant_id'] = restaurant_row['id']
            item['restaurant_name'] = restaurant_row['name']
            item['cuisine'] = restaurant_row.get('cuisine', '')
            featured.append(item)
    reviews = [
        {'name': 'Anika', 'text': 'Bright flavors, quick delivery, and everything arrived warm.'},
        {'name': 'Rahul', 'text': 'The pickup flow was smooth and the naan was fresh.'},
    ]
    rewards = ['Free delivery after two more orders', 'Weekend spice bowl bonus']
    home_content = call(request, 'GET', '/content/home')
    try:
        customer_location = call(request, 'GET', '/customer/location')
    except Exception:
        customer_location = None
    try:
        saved_addresses = call(request, 'GET', '/addresses')
    except Exception:
        saved_addresses = []
    restaurant_sections = {}
    for row in restaurants:
        section_name = row.get('cuisine') or 'Restaurants near you'
        restaurant_sections.setdefault(section_name, []).append(row)
    context = {
        'restaurant_sections': [{'name': name, 'restaurants': rows} for name, rows in restaurant_sections.items()],
        'home_content': home_content,
        'restaurants': restaurants,
        'restaurant_markers': [{'id': row['id'], 'name': row['name'], 'address': row.get('address', ''), 'latitude': row.get('latitude'), 'longitude': row.get('longitude')} for row in restaurants if row.get('address')],
        'pagination': meta,
        'categories': categories,
        'order_mode': order_mode,
        'cart_count': cart_count,
        'customer_location': customer_location,
        'saved_addresses': saved_addresses,
        'cart': cart_data,
        'checkout_restaurant_markers': [{'id': 'restaurant-' + str(group['restaurant_id']), 'name': group['restaurant_name'], 'address': group['restaurant_address']} for group in cart_data.get('groups', []) if group.get('restaurant_address')],
        'active_order': active_order,
        'featured': featured[:8],
        'reviews': reviews,
        'rewards': rewards,
    }
    return render(request,'customer_app/restaurants.html',context)

@protected
@require_http_methods(['GET'])
def search_suggestions(request):
    query = request.GET.get('q', '').strip()[:120]
    if not query:
        return JsonResponse({'items': []})
    return JsonResponse(call(request, 'GET', '/restaurants/suggestions', params={'q': query, 'limit': 12}))

@protected
@require_http_methods(['POST'])
def order_mode(request):
    mode = request.POST.get('mode', '')
    if mode not in {'delivery', 'pickup'}:
        return JsonResponse({'detail': 'Invalid order mode'}, status=400)
    result = call(request, 'POST', '/customer/order-mode', {'mode': mode})
    request.session['order_mode'] = result['mode']
    return JsonResponse({'mode': result['mode']})

@protected
@require_http_methods(['POST'])
def location(request):
    try:
        latitude = float(request.POST.get('latitude', ''))
        longitude = float(request.POST.get('longitude', ''))
    except ValueError:
        return JsonResponse({'detail': 'Invalid location'}, status=400)
    payload = {'latitude': latitude, 'longitude': longitude}
    if 'address' in request.POST:
        payload['address'] = request.POST.get('address', '').strip()
    return JsonResponse(call(request, 'POST', '/customer/location', payload))

@protected
@require_http_methods(['POST'])
def photo(request):
    upload = request.FILES.get('photo')
    if not upload:
        return JsonResponse({'detail': 'Choose a photo'}, status=400)
    result = call(request, 'POST', '/files', {'purpose': 'profile'}, files={'file': (upload.name, upload, upload.content_type)})
    request.session['profile_photo'] = result['id']
    return JsonResponse({'id': result['id'], 'url': f"/customer/files/{result['id']}"})

@protected
def restaurant(request,restaurant_id):
    result = call(request,'GET',f'/restaurants/{restaurant_id}')
    grouped = {}
    featured_ids = {item['id'] for item in result.get('menu', [])[:8]}
    for item in result.get('menu', []):
        if item['id'] not in featured_ids:
            grouped.setdefault(item.get('category') or 'General', []).append(item)
    cover = (result.get('presentation') or {}).get('cover_file_id')
    result['banner_url'] = f'/customer/files/{cover}' if cover else next((item['photo_urls'][0] for item in result.get('menu', []) if item.get('photo_urls')), '')
    result['promotions'] = call(request, 'GET', '/content/promotions')
    result['menu_groups'] = [{'name': name, 'items': items} for name, items in grouped.items()]
    return render(request,'customer_app/restaurant.html',result)

@protected
@require_http_methods(['GET','POST'])
def cart(request):
    if request.method=='POST':
        call(request,'PUT','/cart',{'menu_item_id':request.POST.get('menu_item_id'),'quantity':request.POST.get('quantity'), 'special_instructions':request.POST.get('special_instructions')})
        if request.headers.get('X-Requested-With') == 'fetch':
            data = call(request,'GET','/cart')
            data['cart_count'] = sum(item['quantity'] for item in data.get('items', []))
            return JsonResponse(data)
        next_url = request.POST.get('next','/customer/cart')
        if not next_url.startswith('/customer/'):
            next_url = '/customer/cart'
        return redirect(next_url)
    data = call(request,'GET','/cart')
    data['cart_count'] = sum(item['quantity'] for item in data.get('items', []))
    data['order_mode'] = request.session.get('order_mode','delivery')
    if request.headers.get('X-Requested-With') == 'fetch':
        return JsonResponse(data)
    return render(request,'customer_app/cart.html',data)

@protected
@require_http_methods(['GET','POST'])
def addresses(request,address_id=None):
    rows = call(request,'GET','/addresses')
    current = next((r for r in rows if r['id']==address_id),{})
    form = AddressForm(request.POST or None,initial=current)
    if request.method=='POST':
        if request.POST.get('delete') and address_id:
            call(request,'DELETE',f'/addresses/{address_id}')
            return redirect('/customer/addresses')
        if form.is_valid():
            call(request,'PUT' if address_id else 'POST',f'/addresses/{address_id}' if address_id else '/addresses',form.cleaned_data)
            return redirect('/customer/addresses')
    return render(request,'customer_app/addresses.html',{'form':form,'addresses':rows,'title':'Delivery addresses'})

@protected
@require_http_methods(['GET','POST'])
def checkout(request):
    initial_mode = request.session.get('order_mode', 'delivery')
    addresses_data = call(request, 'GET', '/addresses')
    cart_data = call(request, 'GET', '/cart')
    form = CheckoutForm(
        request.POST or None,
        initial={'request_key': uuid.uuid4().hex, 'mode': initial_mode},
    )
    form.fields['address_id'].choices = [('', 'Choose address')] + [
        (row['id'], row['label'] + ' — ' + row['details'])
        for row in addresses_data
    ]
    if request.method == 'POST' and form.is_valid():
        try:
            mode = form.cleaned_data['mode']
            call(request, 'POST', '/customer/order-mode', {'mode': mode})
            request.session['order_mode'] = mode
            form.cleaned_data['tip'] = str(form.cleaned_data.get('tip') or 0)
            result = call(request, 'POST', '/orders', form.cleaned_data)
            return redirect(f"/customer/order/{result['id']}/track")
        except APIError as exc:
            form.add_error(None, str(exc))

    checkout_mode = request.POST.get('mode', initial_mode)
    if checkout_mode not in {'delivery', 'pickup'}:
        checkout_mode = initial_mode
    promo_code = request.POST.get('promo_code', '').strip()
    try:
        quote = call(
            request,
            'POST',
            '/cart/quote',
            {'mode': checkout_mode, 'promo_code': promo_code or None},
        )
    except APIError as exc:
        quote = call(request, 'POST', '/cart/quote', {'mode': checkout_mode})
        if not form.errors:
            form.add_error('promo_code', str(exc))

    selected_address_id = None
    try:
        selected_address_id = int(request.POST.get('address_id', ''))
    except (TypeError, ValueError):
        if addresses_data:
            selected_address_id = next((row['id'] for row in addresses_data if row['id'] == request.session.get('delivery_address_id')), addresses_data[0]['id'])
    selected_address = next(
        (row for row in addresses_data if row['id'] == selected_address_id),
        None,
    )
    item_count = sum(group.get('item_count', 0) for group in cart_data.get('groups', []))
    return render(request, 'customer_app/checkout.html', {
        'form': form,
        'cart': cart_data,
        'quote': quote,
        'addresses': addresses_data,
        'selected_address': selected_address,
        'selected_address_id': selected_address_id,
        'checkout_mode': checkout_mode,
        'item_count': item_count,
        'checkout_restaurant_markers': [{'id': 'restaurant-' + str(group['restaurant_id']), 'name': group['restaurant_name'], 'address': group['restaurant_address']} for group in cart_data.get('groups', []) if group.get('restaurant_address')],
        'cancellation_policy': call(request,'GET','/cancellation-policy'),
        'title': 'Checkout',
    })


@protected
@require_http_methods(['POST'])
def checkout_quote(request):
    mode = request.POST.get('mode', '')
    if mode not in {'delivery', 'pickup'}:
        return JsonResponse({'detail': 'Invalid order mode'}, status=400)
    try:
        result = call(request, 'POST', '/cart/quote', {
            'mode': mode,
            'promo_code': request.POST.get('promo_code', '').strip() or None,
            'tip': request.POST.get('tip') or '0',
        })
        return JsonResponse(result)
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)


@protected
@require_http_methods(['POST'])
def reorder(request,order_id):
    call(request,'POST',f'/orders/{order_id}/reorder')
    return redirect('/customer/cart')

@protected
@require_http_methods(['GET','POST'])
def review(request,order_id):
    form = ReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        result = call(request,'POST',f'/orders/{order_id}/review',form.cleaned_data)
        messages.success(request,f"Review saved. Upload a review photo using review ID {result['id']}.")
        return redirect('/customer/files')
    return render(request,'form.html',{'form':form,'title':'Review your order'})

@protected
@require_http_methods(['GET'])
def checkout_eta(request):
    try:
        return JsonResponse(call(request, 'GET', '/cart/eta', params={
            'mode': request.GET.get('mode', 'delivery'),
            **({'address_id': request.GET['address_id']} if request.GET.get('address_id') else {}),
        }))
    except APIError as exc:
        return JsonResponse({'detail': str(exc)}, status=exc.status)

@protected
@require_http_methods(['GET', 'POST'])
def address_book(request):
    if request.method == 'POST':
        address_id = request.POST.get('id')
        payload = {'label': request.POST.get('label', 'Home'), 'details': request.POST.get('address', ''),
                   'is_default': request.POST.get('is_default') == 'on'}
        payload.update({'id': address_id or None, 'latitude': request.POST.get('latitude'),
                        'longitude': request.POST.get('longitude')})
        result = call(request, 'POST', '/addresses/select', payload)
        request.session['delivery_address_id'] = result['id']
        return JsonResponse(result)
    return JsonResponse({'addresses': call(request, 'GET', '/addresses'),
                         'location': call(request, 'GET', '/customer/location')})

@protected
@require_http_methods(['GET', 'POST'])
def notification_panel(request):
    if request.method == 'POST':
        notification_id = request.POST.get('id', '')
        if not notification_id.isdigit():
            return JsonResponse({'detail': 'Invalid notification'}, status=400)
        return JsonResponse(call(request, 'POST', f'/operations/notifications/{notification_id}/read'))
    return JsonResponse(call(request, 'GET', '/operations/notifications'), safe=False)

@protected
@require_http_methods(['GET'])
def order_availability(request, entity, entity_id):
    path = 'restaurants' if entity == 'restaurant' else 'menu'
    return JsonResponse(call(request, 'GET', f'/{path}/{entity_id}/order-availability'), headers={'Cache-Control':'no-store'})
