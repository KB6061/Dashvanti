from fastapi import HTTPException
from sqlalchemy import select
from backend.models import Restaurant, RestaurantPresentation, MenuItem, File

def accepting(db, restaurant):
    if not restaurant or not restaurant.is_open:
        return False
    presentation = db.get(RestaurantPresentation, restaurant.id)
    return not presentation or presentation.busy_mode != 'paused'

def status(db, restaurant_id):
    restaurant = db.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(404, 'Restaurant not found')
    opened = accepting(db, restaurant)
    alternatives = []
    if not opened:
        candidates = db.scalars(select(Restaurant).where(Restaurant.is_open == True, Restaurant.id != restaurant_id).order_by(Restaurant.id).limit(100))
        for candidate in candidates:
            if not accepting(db, candidate):
                continue
            photo = db.scalar(select(File.id).join(MenuItem, File.entity_id == MenuItem.id).where(File.purpose == 'menu', MenuItem.restaurant_id == candidate.id, MenuItem.available == True).order_by(File.id.desc()).limit(1))
            alternatives.append({'id':candidate.id,'name':candidate.name,'cuisine':candidate.cuisine,'address':candidate.address,'photo_id':photo,'similar':candidate.cuisine == restaurant.cuisine})
        alternatives.sort(key=lambda row: not row['similar'])
    return {'restaurant_id':restaurant.id,'name':restaurant.name,'is_open':opened,'alternatives':alternatives[:20]}

def menu_status(db, item_id):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, 'Menu item not found')
    return status(db, item.restaurant_id)
