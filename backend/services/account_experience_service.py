from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.models import User, Restaurant, MenuItem, RestaurantPresentation, Order, Review, Rating, File, CustomerLocation, Promotion, now
from backend.customer_account_models import CustomerFavorite, CustomerProfile, CustomerWalletTransaction
from backend.account_enhancement_models import MenuFavorite, ReviewPublication, ReviewHelpful, ReviewReport, EntityVerification, PromotionRegion, RestaurantRegion


def verified(db, user_id):
    row = db.get(EntityVerification, user_id)
    if row:
        return row.verified
    user = db.get(User, user_id)
    if user and user.role == 'customer':
        from backend.social_models import SocialIdentity
        return bool(db.scalar(select(SocialIdentity.id).where(SocialIdentity.user_id == user_id, SocialIdentity.provider == 'google')))
    return False


def avatar(db, user_id):
    photo = db.scalar(select(File.id).where(File.user_id == user_id, File.purpose == 'profile').order_by(File.id.desc()))
    if photo:
        return {'photo_id': photo, 'url': '/api/account-experience/avatar/' + str(user_id)}
    from backend.social_models import SocialIdentity
    social = db.scalar(select(SocialIdentity).where(SocialIdentity.user_id == user_id).order_by(SocialIdentity.last_login_at.desc()))
    return {'photo_id': None, 'url': social.profile_picture if social and social.profile_picture else ''}


def avatar_file(db, viewer, user_id):
    owner = db.get(User, user_id)
    if not owner:
        raise HTTPException(404, 'Profile photo not found')
    allowed = bool(viewer and (viewer.id == user_id or viewer.role == 'admin')) or owner.role == 'restaurant'
    if owner.role == 'customer':
        allowed |= bool(db.scalar(select(Review.id).join(ReviewPublication, ReviewPublication.review_id == Review.id).where(Review.customer_id == user_id, ReviewPublication.status == 'approved').limit(1)))
    if not allowed and viewer:
        scope = {'customer': Order.customer_id, 'restaurant': Order.restaurant_id, 'driver': Order.driver_id}.get(viewer.role)
        if scope is not None:
            target = Order.driver_id if owner.role == 'driver' else Order.customer_id
            allowed = bool(db.scalar(select(Order.id).where(scope == viewer.id, target == user_id).limit(1)))
    if not allowed:
        raise HTTPException(404, 'Profile photo not found')
    row = db.scalar(select(File).where(File.user_id == user_id, File.purpose == 'profile').order_by(File.id.desc()))
    if not row:
        raise HTTPException(404, 'Profile photo not found')
    from backend.config import settings
    path = Path(row.path).resolve()
    if not path.is_relative_to(Path(settings.file_root).resolve()) or not path.is_file():
        raise HTTPException(404, 'Profile photo not found')
    from backend.services.file_service import thumbnail_path
    return thumbnail_path(path)


def review_photo(db, viewer, file_id):
    file = db.get(File, file_id)
    publication = db.get(ReviewPublication, file.entity_id) if file and file.purpose == 'review' else None
    if not file or not publication:
        raise HTTPException(404, 'Photo not found')
    if publication.status != 'approved' and not (viewer and (viewer.role == 'admin' or viewer.id == file.user_id)):
        raise HTTPException(404, 'Photo not found')
    from backend.config import settings
    path = Path(file.path).resolve()
    if not path.is_relative_to(Path(settings.file_root).resolve()) or not path.is_file():
        raise HTTPException(404, 'Photo not found')
    from backend.services.file_service import thumbnail_path
    return thumbnail_path(path)


def favorites(db, user):
    rows = []
    stores = db.scalars(select(Restaurant).join(CustomerFavorite, CustomerFavorite.restaurant_id == Restaurant.id).where(CustomerFavorite.customer_id == user.id))
    for store in stores:
        cover = db.get(RestaurantPresentation, store.id)
        rating = db.scalar(select(func.avg(Rating.restaurant)).join(Order, Rating.order_id == Order.id).where(Order.restaurant_id == store.id))
        rows.append({'id': store.id, 'name': store.name, 'cuisine': store.cuisine, 'rating': float(rating or 0),
                     'delivery_minutes': store.delivery_minutes, 'verified': verified(db, store.id),
                     'photo_id': (cover.cover_file_id or cover.logo_file_id) if cover else None})
    items = []
    for item, store in db.execute(select(MenuItem, Restaurant).join(Restaurant, Restaurant.id == MenuItem.restaurant_id).join(MenuFavorite, MenuFavorite.menu_item_id == MenuItem.id).where(MenuFavorite.customer_id == user.id)):
        photo = db.scalar(select(File.id).where(File.purpose == 'menu', File.entity_id == item.id).order_by(File.id.desc()))
        rating = db.scalar(select(func.avg(Rating.restaurant)).join(Order, Rating.order_id == Order.id).where(Order.restaurant_id == store.id))
        items.append({'id': item.id, 'name': item.name, 'restaurant_id': store.id, 'restaurant': store.name,
                      'price': item.price, 'currency': store.currency, 'photo_id': photo, 'cuisine': store.cuisine,
                      'rating': float(rating or 0), 'delivery_minutes': store.delivery_minutes, 'available': item.available})
    return {'restaurants': rows, 'menu_items': items}


def favorite(db, user, data):
    from backend.models import Customer
    db.scalar(select(Customer).where(Customer.id == user.id).with_for_update())
    model, target, field = (CustomerFavorite, Restaurant, 'restaurant_id') if data.kind == 'restaurant' else (MenuFavorite, MenuItem, 'menu_item_id')
    if not db.get(target, data.target_id):
        raise HTTPException(404, 'Favorite target not found')
    row = db.get(model, (user.id, data.target_id))
    if data.enabled and not row:
        db.add(model(customer_id=user.id, **{field: data.target_id}))
    elif not data.enabled and row:
        db.delete(row)
    db.flush()
    return {'favorite': data.enabled}


def review_save(db, user, data):
    order = db.get(Order, data.order_id)
    if not order or order.customer_id != user.id or order.status not in {'DELIVERED', 'COMPLETED'}:
        raise HTTPException(403, 'Only your completed orders can be reviewed')
    if not data.comment.strip():
        raise HTTPException(422, 'Enter a review comment')
    row = db.scalar(select(Review).where(Review.order_id == order.id))
    if not row:
        row = Review(order_id=order.id, customer_id=user.id, text=data.comment.strip())
        db.add(row)
        db.flush()
    else:
        row.text = data.comment.strip()
    rating = db.scalar(select(Rating).where(Rating.order_id == order.id))
    if not rating:
        rating = Rating(order_id=order.id)
        db.add(rating)
    rating.restaurant = data.rating
    publication = db.get(ReviewPublication, row.id)
    if not publication:
        publication = ReviewPublication(review_id=row.id)
        db.add(publication)
    publication.title, publication.status = data.title.strip(), 'pending'
    publication.moderated_at = None
    db.flush()
    return {'id': row.id, 'message': 'Review submitted for approval. Photos are optional.'}


def review_action(db, user, review_id, data):
    row = db.scalar(select(Review).where(Review.id == review_id).with_for_update())
    publication = db.get(ReviewPublication, review_id)
    if not row or not publication:
        raise HTTPException(404, 'Review not found')
    if data.action in {'approve', 'reject'}:
        from backend.services.incident_service import permission
        permission(db, user, 'review_moderate')
        publication.status = 'approved' if data.action == 'approve' else 'rejected'
        publication.moderator_id, publication.moderated_at = user.id, now()
        db.info['audit_reason'] = data.reason
    else:
        if publication.status != 'approved':
            raise HTTPException(404, 'Review not found')
        if data.action == 'helpful':
            if row.customer_id == user.id:
                raise HTTPException(409, 'You cannot vote on your own review')
            vote = db.get(ReviewHelpful, (review_id, user.id))
            if vote:
                db.delete(vote)
            else:
                db.add(ReviewHelpful(review_id=review_id, user_id=user.id))
        elif data.action == 'report':
            if not data.reason.strip():
                raise HTTPException(422, 'Enter a reason')
            report = db.get(ReviewReport, (review_id, user.id))
            if not report:
                db.add(ReviewReport(review_id=review_id, user_id=user.id, reason=data.reason.strip()))
    db.flush()
    return {'message': 'Review action saved'}


def reviews(db, restaurant_id=None, admin=False, page=1, size=25):
    query = select(Review, ReviewPublication, Order, Rating.restaurant, User).join(ReviewPublication, ReviewPublication.review_id == Review.id).join(Order, Order.id == Review.order_id).join(User, User.id == Review.customer_id).outerjoin(Rating, Rating.order_id == Order.id)
    if restaurant_id:
        query = query.where(Order.restaurant_id == restaurant_id)
    if not admin:
        query = query.where(ReviewPublication.status == 'approved')
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = []
    for review, publication, order, rating, author in db.execute(query.order_by(Review.id.desc()).offset((page-1)*size).limit(size)):
        photos = list(db.scalars(select(File.id).where(File.purpose == 'review', File.entity_id == review.id).order_by(File.id).limit(5)))
        items.append({'id': review.id, 'restaurant_id': order.restaurant_id, 'name': author.name, 'avatar': avatar(db, author.id)['url'],
                      'rating': rating, 'title': publication.title, 'text': review.text, 'created_at': publication.created_at,
                      'verified': order.status in {'DELIVERED', 'COMPLETED'}, 'photos': photos, 'status': publication.status,
                      'helpful': db.scalar(select(func.count()).select_from(ReviewHelpful).where(ReviewHelpful.review_id == review.id)),
                      'reports': db.scalar(select(func.count()).select_from(ReviewReport).where(ReviewReport.review_id == review.id)) if admin else None})
    return {'items': items, 'total': total, 'page': page, 'size': size}


def promotion_allowed(db, promotion, user):
    region = db.get(PromotionRegion, promotion.id)
    profile = db.get(CustomerProfile, user.id)
    return bool(region and region.country == user.country and (not region.city or profile and region.city.casefold() == profile.city.casefold()))


def initialize_profile(db, user, request=None):
    from backend.services.customer_account_service import record
    profile = record(db, CustomerProfile, user)
    if not request:
        return profile
    from backend.services.account_location_service import ip_profile
    found = ip_profile(request)
    if found:
        if not user.country:
            user.country = found.get('country')
        if not profile.city:
            profile.city = found.get('city', '')
            profile.state = found.get('state', '')
        if not profile.timezone_detected and found.get('timezone'):
            profile.timezone = found['timezone']
    language = request.headers.get('accept-language', '').split(',')[0].split(';')[0].strip()
    if language:
        profile.language = language[:20]
    return profile


def snapshot_extra(db, user):
    from backend.services.account_gateway_service import methods
    favorite_data = favorites(db, user)
    return {'favorites_detail': favorite_data, 'gateways': methods(db, user), 'avatar': avatar(db, user.id)['url'],
            'verified': verified(db, user.id), 'wallet_refunds': db.scalar(select(func.coalesce(func.sum(CustomerWalletTransaction.amount), 0)).where(CustomerWalletTransaction.customer_id == user.id, CustomerWalletTransaction.currency == ('INR' if user.country == 'IN' else 'USD'), CustomerWalletTransaction.kind == 'refund'))}
