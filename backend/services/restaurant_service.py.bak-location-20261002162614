from fastapi import HTTPException
from sqlalchemy import select, func, or_
from backend.models import Restaurant, MenuItem, Rating, Review, Order, User, File, RestaurantPresentation
from backend.services.kafka_event_service import emit


def _clock_label(value):
    try:
        hour, minute = (int(part) for part in str(value).split(':', 1))
    except (TypeError, ValueError):
        return str(value or '')
    suffix = 'AM' if hour < 12 else 'PM'
    return f'{hour % 12 or 12}:{minute:02d} {suffix}'

def browse(db, q='', cuisine='', veg=False, rating=0, delivery_time=240, page=1, page_size=24):
    stmt = select(Restaurant).where(Restaurant.delivery_minutes <= delivery_time)
    query = q.strip().lower()
    term = f'%{query}%' if query else ''
    if cuisine:
        stmt = stmt.where(func.lower(Restaurant.cuisine) == cuisine.lower())
    if term:
        stmt = stmt.where(or_(
            func.lower(Restaurant.name).like(term),
            func.lower(Restaurant.cuisine).like(term),
            Restaurant.id.in_(select(MenuItem.restaurant_id).where(
                MenuItem.available == True,
                or_(
                    func.lower(MenuItem.name).like(term),
                    func.lower(MenuItem.description).like(term),
                    func.lower(MenuItem.category).like(term),
                ),
            )),
        ))
    if veg:
        stmt = stmt.where(Restaurant.id.in_(select(MenuItem.restaurant_id).where(
            MenuItem.veg == True,
            MenuItem.available == True,
        )))
    total_count = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    restaurant_rows = list(db.scalars(
        stmt.order_by(Restaurant.name).offset((page - 1) * page_size).limit(page_size)
    ))
    restaurant_ids = [row.id for row in restaurant_rows]
    if not restaurant_ids:
        return {'items': [], 'meta': {'page': page, 'page_size': page_size, 'total': total_count}}

    rating_rows = db.execute(
        select(Order.restaurant_id, func.avg(Rating.restaurant), func.count(Rating.id))
        .select_from(Order)
        .join(Rating, Rating.order_id == Order.id)
        .where(Order.restaurant_id.in_(restaurant_ids))
        .group_by(Order.restaurant_id)
    ).all()
    ratings = {
        restaurant_id: {'average': float(score or 0), 'count': int(count or 0)}
        for restaurant_id, score, count in rating_rows
    }

    price_rows = db.execute(
        select(MenuItem.restaurant_id, func.min(MenuItem.price), func.max(MenuItem.price))
        .where(MenuItem.restaurant_id.in_(restaurant_ids), MenuItem.available == True)
        .group_by(MenuItem.restaurant_id)
    ).all()
    prices = {
        restaurant_id: {'min': minimum or 0, 'max': maximum or 0}
        for restaurant_id, minimum, maximum in price_rows
    }

    presentation_rows = list(db.scalars(
        select(RestaurantPresentation).where(
            RestaurantPresentation.restaurant_id.in_(restaurant_ids)
        )
    ))
    presentations = {row.restaurant_id: row for row in presentation_rows}
    restaurants_by_id = {row.id: row for row in restaurant_rows}
    menu_by_restaurant = {restaurant_id: [] for restaurant_id in restaurant_ids}
    menu_rows = list(db.scalars(
        select(MenuItem)
        .where(MenuItem.restaurant_id.in_(restaurant_ids), MenuItem.available == True)
        .order_by(MenuItem.restaurant_id, MenuItem.name)
    ))
    for menu_item in menu_rows:
        restaurant_row = restaurants_by_id[menu_item.restaurant_id]
        restaurant_matches = query and query in (
            f'{restaurant_row.name} {restaurant_row.cuisine or ""}'.lower()
        )
        menu_text = f'{menu_item.name} {menu_item.description or ""} {menu_item.category or ""}'.lower()
        if query and not restaurant_matches and query not in menu_text:
            continue
        items = menu_by_restaurant[menu_item.restaurant_id]
        if len(items) < 100:
            items.append(menu_item)

    displayed_menu_ids = [
        menu_item.id
        for items in menu_by_restaurant.values()
        for menu_item in items
    ]
    photo_ids = {}
    if displayed_menu_ids:
        photo_rows = db.execute(
            select(File.entity_id, func.max(File.id))
            .where(File.purpose == 'menu', File.entity_id.in_(displayed_menu_ids))
            .group_by(File.entity_id)
        ).all()
        photo_ids = dict(photo_rows)

    results = []
    for row in restaurant_rows:
        rating_summary = ratings.get(row.id, {'average': 0, 'count': 0})
        score = rating_summary['average']
        if score < rating:
            continue
        menu_matches = []
        for menu_item in menu_by_restaurant[row.id]:
            photo_id = photo_ids.get(menu_item.id)
            menu_matches.append({
                'id': menu_item.id,
                'name': menu_item.name,
                'description': menu_item.description or '',
                'price': menu_item.price,
                'veg': menu_item.veg,
                'category': menu_item.category or 'General',
                'restaurant_name': row.name,
                'photo_url': f'/customer/files/{photo_id}' if photo_id else '',
            })
        presentation = presentations.get(row.id)
        results.append({
            'id': row.id,
            'name': row.name,
            'description': row.description or '',
            'address': row.address or '',
            'cuisine': row.cuisine,
            'kind': row.kind,
            'is_open': row.is_open,
            'opening': row.opening,
            'closing': row.closing,
            'opening_label': _clock_label(row.opening),
            'closing_label': _clock_label(row.closing),
            'delivery_minutes': row.delivery_minutes,
            'rating': round(score, 1),
            'rating_count': rating_summary['count'],
            'price_range': prices.get(row.id, {'min': 0, 'max': 0}),
            'matches': menu_matches,
            'presentation': {
                'cover_file_id': presentation.cover_file_id,
                'logo_file_id': presentation.logo_file_id,
            } if presentation else {},
        })
    return {
        'items': results,
        'meta': {'page': page, 'page_size': page_size, 'total': total_count},
    }


def search_suggestions(db, q, limit=12):
    query = q.strip().lower()
    if not query:
        return []
    term = f'%{query}%'
    suggestions = []
    restaurants = list(db.scalars(
        select(Restaurant).where(or_(
            func.lower(Restaurant.name).like(term),
            func.lower(Restaurant.cuisine).like(term),
        )).limit(limit * 2)
    ))
    for row in restaurants:
        if query in row.name.lower():
            suggestions.append({
                'type': 'restaurant',
                'label': row.name,
                'value': row.name,
                'subtitle': f'Restaurant · {row.cuisine}',
                'restaurant_id': row.id,
            })
    cuisines = list(db.scalars(
        select(Restaurant.cuisine)
        .where(func.lower(Restaurant.cuisine).like(term))
        .distinct()
        .limit(limit)
    ))
    for cuisine in cuisines:
        suggestions.append({
            'type': 'cuisine',
            'label': cuisine,
            'value': cuisine,
            'subtitle': 'Cuisine',
        })
    menu_rows = db.execute(
        select(MenuItem, Restaurant.name)
        .join(Restaurant, Restaurant.id == MenuItem.restaurant_id)
        .where(
            MenuItem.available == True,
            or_(
                func.lower(MenuItem.name).like(term),
                func.lower(MenuItem.category).like(term),
            ),
        )
        .limit(limit * 2)
    ).all()
    for item, restaurant_name in menu_rows:
        suggestions.append({
            'type': 'menu',
            'label': item.name,
            'value': item.name,
            'subtitle': f'Menu · {restaurant_name}',
            'restaurant_id': item.restaurant_id,
        })
    unique = {}
    for item in suggestions:
        unique.setdefault((item['type'], item['value'].lower()), item)
    type_order = {'menu': 0, 'restaurant': 1, 'cuisine': 2}
    def rank(item):
        value = item['value'].lower()
        match = 0 if value == query else 1 if value.startswith(query) else 2
        return match, type_order[item['type']], value
    return sorted(unique.values(), key=rank)[:limit]


def detail(db, restaurant_id):
    row = db.get(Restaurant, restaurant_id)
    if not row:
        raise HTTPException(404, 'Restaurant not found')
    reviews = list(db.scalars(select(Review).join(Order, Review.order_id == Order.id).where(Order.restaurant_id == row.id).order_by(Review.id.desc()).limit(50)))
    menu = list(db.scalars(select(MenuItem).where(MenuItem.restaurant_id == row.id, MenuItem.available == True)))
    def photos(purpose, entity_id):
        return list(db.scalars(select(File.id).where(File.purpose == purpose, File.entity_id == entity_id).order_by(File.id.desc()).limit(5)))
    score = db.scalar(select(func.avg(Rating.restaurant)).join(Order, Rating.order_id == Order.id).where(Order.restaurant_id == row.id)) or 0
    prices = db.execute(select(func.min(MenuItem.price), func.max(MenuItem.price)).where(MenuItem.restaurant_id == row.id, MenuItem.available == True)).one()
    def photo_urls(ids, portal='customer'):
        return [f'/{portal}/files/{file_id}' for file_id in ids]
    profile_photos = photos('profile', row.id)
    menu_rows = []
    for m in menu:
        menu_photos = photos('menu', m.id)
        menu_rows.append({'id': m.id, 'name': m.name, 'description': m.description, 'price': m.price, 'veg': m.veg, 'category': m.category or 'General', 'photos': menu_photos, 'photo_urls': photo_urls(menu_photos)})
    presentation = db.get(RestaurantPresentation, row.id)
    presentation_data = {'cover_file_id': presentation.cover_file_id, 'logo_file_id': presentation.logo_file_id, 'gallery_file_ids': __import__('json').loads(presentation.gallery_file_ids or '[]'), 'busy_mode': presentation.busy_mode, 'busy_until': presentation.busy_until, 'prep_extra_minutes': presentation.prep_extra_minutes} if presentation else {}
    owner = db.get(User, row.id)
    return {'phone': owner.phone if owner else '', 'opening_label': _clock_label(row.opening), 'closing_label': _clock_label(row.closing), 'restaurant': row, 'photos': profile_photos, 'photo_urls': photo_urls(profile_photos), 'presentation': presentation_data, 'rating': round(float(score), 1), 'price_range': {'min': prices[0] or 0, 'max': prices[1] or 0}, 'menu': menu_rows, 'reviews': [{'id': r.id, 'text': r.text, 'photos': photos('review', r.id), 'photo_urls': photo_urls(photos('review', r.id))} for r in reviews]}

def update(db, user, data):
    row = db.get(Restaurant, user.id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    return row

def update_hours(db, user, data):
    row = db.scalar(select(Restaurant).where(Restaurant.id == user.id).with_for_update())
    row.opening = data.opening
    row.closing = data.closing
    emit(db, 'RESTAURANT_HOURS_UPDATED', {'restaurant_id': row.id, 'opening': row.opening, 'closing': row.closing})
    return row

def toggle_availability(db, user, data):
    row = db.scalar(select(Restaurant).where(Restaurant.id == user.id).with_for_update())
    row.is_open = data.is_open
    emit(db, 'RESTAURANT_AVAILABILITY_CHANGED', {'restaurant_id': row.id, 'is_open': row.is_open})
    return row

def availability(db, restaurant_id):
    row = db.get(Restaurant, restaurant_id)
    if not row:
        raise HTTPException(404, 'Restaurant not found')
    return {'restaurant_id': row.id, 'is_open': row.is_open, 'opening': row.opening, 'closing': row.closing, 'delivery_minutes': row.delivery_minutes}
