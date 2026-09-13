from fastapi import APIRouter, Depends, UploadFile, File as UploadField, Form, Query, Response
from fastapi.responses import FileResponse
from backend.db import get_db
from sqlalchemy import select
from backend.models import Customer, Restaurant, Driver, File
from backend.schemas import OrderSoundPreference, RouteDistanceInput, AddressSelection, Profile, AddressInput, RestaurantInput, RestaurantHours, RestaurantAvailability, MenuInput, CartInput, OrderMode, CustomerLocationInput, CheckoutQuote, Checkout, Transition, ReviewInput, Availability, DriverProfile, DriverLocationInput
from backend.security import current_user, role
from backend.services import user_service, restaurant_service, menu_service, order_service, delivery_service, file_service

router = APIRouter()
customer = role('customer')
restaurant = role('restaurant')
driver = role('driver')

@router.get('/me')
def me(user=Depends(current_user), db=Depends(get_db, scope='function')):
    profile_photo = db.scalar(select(File.id).where(File.user_id == user.id, File.purpose == 'profile').order_by(File.id.desc()))
    customer_profile = db.get(Customer, user.id) if user.role == 'customer' else None
    return {'id':user.id, 'email':user.email, 'name':user.name, 'phone':user.phone, 'role':user.role, 'profile_photo':profile_photo, 'order_mode':customer_profile.order_mode if customer_profile else None, 'restaurant':db.get(Restaurant,user.id) if user.role=='restaurant' else None, 'driver':db.get(Driver,user.id) if user.role=='driver' else None}

@router.put('/me')
def profile(data: Profile, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return user_service.update_profile(db,user,data)

@router.get('/addresses')
def addresses(user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.addresses(db,user)

@router.post('/addresses', status_code=201)
def add_address(data: AddressInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.save_address(db,user,data)

@router.put('/addresses/{address_id}')
def edit_address(address_id: int, data: AddressInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.save_address(db,user,data,address_id)

@router.delete('/addresses/{address_id}')
def delete_address(address_id: int, user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.delete_address(db,user,address_id)

@router.get('/restaurants')
def restaurants(q: str = Query('',max_length=120), cuisine: str = '', veg: bool = False, rating: float = Query(0,ge=0,le=5), delivery_time: int = Query(240,ge=5,le=240), page: int = Query(1,ge=1), page_size: int = Query(24,ge=1,le=100), db=Depends(get_db, scope='function')):
    return restaurant_service.browse(db,q,cuisine,veg,rating,delivery_time,page,page_size)

@router.get('/restaurants/suggestions')
def restaurant_suggestions(q: str = Query('', min_length=1, max_length=120), limit: int = Query(12, ge=1, le=20), db=Depends(get_db, scope='function')):
    return {'items': restaurant_service.search_suggestions(db, q, limit)}

@router.get('/restaurants/{restaurant_id}')
def restaurant_detail(restaurant_id: int, db=Depends(get_db, scope='function')):
    return restaurant_service.detail(db,restaurant_id)

@router.put('/restaurant/profile')
def restaurant_profile(data: RestaurantInput, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return restaurant_service.update(db,user,data)

@router.post('/restaurant/hours/update')
def restaurant_hours(data: RestaurantHours, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return restaurant_service.update_hours(db,user,data)

@router.post('/restaurant/availability/toggle')
def restaurant_availability(data: RestaurantAvailability, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return restaurant_service.toggle_availability(db,user,data)

@router.get('/restaurant/{restaurant_id}/availability')
def restaurant_availability_status(restaurant_id: int, db=Depends(get_db, scope='function')):
    return restaurant_service.availability(db,restaurant_id)

@router.get('/menu')
def menu(user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return menu_service.listing(db,user)

@router.post('/menu', status_code=201)
def add_menu(data: MenuInput, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return menu_service.save(db,user,data)

@router.put('/menu/{item_id}')
def edit_menu(item_id: int, data: MenuInput, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return menu_service.save(db,user,data,item_id)

@router.delete('/menu/{item_id}')
def remove_menu(item_id: int, user=Depends(restaurant), db=Depends(get_db, scope='function')):
    return menu_service.remove(db,user,item_id)

@router.get('/cart')
def cart(user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.cart(db,user)

@router.put('/cart')
def update_cart(data: CartInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.update_cart(db,user,data)

@router.post('/cart/quote')
def cart_quote(data: CheckoutQuote, user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.checkout_quote(db, user, data)

@router.post('/customer/order-mode')
def customer_order_mode(data: OrderMode, user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.save_order_mode(db,user,data)

@router.get('/customer/location')
def customer_location(user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.current_location(db, user)

@router.post('/customer/location')
def save_customer_location(data: CustomerLocationInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return user_service.save_current_location(db, user, data)

@router.post('/orders', status_code=201)
def checkout(data: Checkout, user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.checkout(db,user,data)

@router.get('/orders')
def orders(user=Depends(current_user), db=Depends(get_db, scope='function')):
    return order_service.listing(db,user)

@router.get('/orders/{order_id}')
def order_detail(order_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return order_service.detail(db,user,order_id)

@router.post('/orders/{order_id}/status')
def status(order_id: int, data: Transition, user=Depends(role('restaurant','driver')), db=Depends(get_db, scope='function')):
    return delivery_service.transition(db,user,order_id,data.status)

@router.post('/orders/{order_id}/reorder')
def reorder(order_id: int, user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.reorder(db,user,order_id)

@router.post('/orders/{order_id}/review', status_code=201)
def review(order_id: int, data: ReviewInput, user=Depends(customer), db=Depends(get_db, scope='function')):
    return order_service.review(db,user,order_id,data)

@router.get('/delivery/available')
def available(user=Depends(driver), db=Depends(get_db, scope='function')):
    return delivery_service.available(db,user)

@router.post('/delivery/{order_id}/accept')
def accept(order_id: int, user=Depends(driver), db=Depends(get_db, scope='function')):
    return delivery_service.accept(db,user,order_id)

@router.put('/delivery/availability')
def availability(data: Availability, user=Depends(driver), db=Depends(get_db, scope='function')):
    return delivery_service.online(db,user,data)

@router.put('/driver/profile')
def driver_profile(data: DriverProfile, user=Depends(driver), db=Depends(get_db, scope='function')):
    return delivery_service.update_profile(db,user,data)

@router.post('/driver/location/update')
def driver_location(data: DriverLocationInput, user=Depends(driver), db=Depends(get_db, scope='function')):
    return delivery_service.update_location(db,user,data)

@router.get('/order/{order_id}/driver/location')
def order_driver_location(order_id: int, response: Response, user=Depends(current_user), db=Depends(get_db, scope='function')):
    response.headers['Cache-Control']='no-store'
    return delivery_service.location_for_order(db,user,order_id)

@router.get('/stats')
def stats(period: str = 'daily', user=Depends(role('restaurant','driver')), db=Depends(get_db, scope='function')):
    return delivery_service.stats(db,user,period)

@router.get('/files')
def files(user=Depends(current_user), db=Depends(get_db, scope='function')):
    return file_service.listing(db,user)

@router.post('/files', status_code=201)
def upload(file: UploadFile = UploadField(...), purpose: str = Form(...), entity_id: int | None = Form(None), user=Depends(current_user), db=Depends(get_db, scope='function')):
    return file_service.upload(db,user,file,purpose,entity_id)

@router.get('/files/{file_id}')
def download(file_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return FileResponse(file_service.download(db,user,file_id), media_type='image/jpeg', headers={'X-Content-Type-Options':'nosniff'})

@router.get('/files/{file_id}/thumbnail')
def thumbnail(file_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return FileResponse(file_service.thumbnail(db, user, file_id), media_type='image/jpeg', headers={'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=86400'})

@router.get('/cart/eta')
def checkout_eta(address_id: int | None = None, mode: str = 'delivery', user=Depends(customer), db=Depends(get_db, scope='function')):
    from backend.services.eta_service import checkout_eta
    return checkout_eta(db, user, address_id, mode)


@router.post('/addresses/select')
def select_address(data: AddressSelection, user=Depends(customer), db=Depends(get_db, scope='function')):
    address = user_service.save_address(db, user, AddressInput(**data.model_dump()), data.id)
    user_service.save_current_location(db, user, CustomerLocationInput(latitude=data.latitude, longitude=data.longitude, address=data.details))
    return address


@router.post('/routes/distance')
def route_distance(data: RouteDistanceInput, user=Depends(current_user)):
    from backend.services.eta_service import route
    return route((data.origin.latitude, data.origin.longitude),
                 (data.destination.latitude, data.destination.longitude))


@router.get('/me/order-sound')
def get_order_sound(user=Depends(current_user)):
    return {'enabled': bool(user.order_sound_enabled), 'user_id': user.id}

@router.put('/me/order-sound')
def update_order_sound(data: OrderSoundPreference, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return user_service.set_order_sound(db, user, data.enabled)

@router.get('/restaurants/{restaurant_id}/order-availability')
def order_availability(restaurant_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    from backend.services.store_status_service import status
    return status(db, restaurant_id)

@router.get('/menu/{item_id}/order-availability')
def menu_order_availability(item_id: int, user=Depends(current_user), db=Depends(get_db, scope='function')):
    from backend.services.store_status_service import menu_status
    return menu_status(db, item_id)
