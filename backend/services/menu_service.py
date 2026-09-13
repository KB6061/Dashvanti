from fastapi import HTTPException
from sqlalchemy import select
from backend.models import MenuItem, File

def listing(db, user):
    rows = list(db.scalars(select(MenuItem).where(MenuItem.restaurant_id == user.id).order_by(MenuItem.id)))
    return [_as_dict(db, row) for row in rows]

def save(db, user, data, item_id=None):
    row = db.get(MenuItem, item_id) if item_id else MenuItem(restaurant_id=user.id)
    if not row or row.restaurant_id != user.id:
        raise HTTPException(404, 'Menu item not found')
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return _as_dict(db, row)

def remove(db, user, item_id):
    row = db.get(MenuItem, item_id)
    if not row or row.restaurant_id != user.id:
        raise HTTPException(404, 'Menu item not found')
    row.available = False
    return {'message': 'Menu item disabled'}

def _as_dict(db, row):
    photos = list(db.scalars(select(File.id).where(File.purpose == 'menu', File.entity_id == row.id).order_by(File.id.desc()).limit(5)))
    return {
        'id': row.id,
        'restaurant_id': row.restaurant_id,
        'name': row.name,
        'description': row.description,
        'category': row.category or 'General',
        'price': row.price,
        'veg': row.veg,
        'available': row.available,
        'photos': photos,
        'photo_urls': [f'/restaurant/files/{file_id}' for file_id in photos],
    }
