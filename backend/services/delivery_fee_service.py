import json
import math
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from backend.models import Address, AuditEvent, Restaurant, now
from backend.delivery_fee_models import Country, CountryDeliverySettings, DeliverySurgeRule, OrderDeliveryFeeSnapshot
from backend.services.geo_service import normalize_country


def money(value):
    return Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def region(value):
    return (value or '').strip().casefold()


def configuration(db):
    countries = list(db.scalars(select(Country).order_by(Country.country_code)))
    settings = list(db.scalars(select(CountryDeliverySettings).order_by(CountryDeliverySettings.country_code, CountryDeliverySettings.state, CountryDeliverySettings.city)))
    return {'countries': countries, 'settings': [settings_view(row) for row in settings],
            'surges': list(db.scalars(select(DeliverySurgeRule).order_by(DeliverySurgeRule.id.desc())))}


def settings_view(row):
    fields = ('id', 'country_code', 'state', 'city', 'currency_code', 'base_fee', 'small_order_threshold',
              'small_order_fee', 'free_delivery_threshold', 'free_delivery_max_distance', 'service_fee_percent', 'active', 'updated_at')
    return {**{key: getattr(row, key) for key in fields}, 'distance_tiers': json.loads(row.distance_tiers)}


def save_country(db, data):
    row = db.scalar(select(Country).where(Country.country_code == data.country_code).with_for_update())
    if row and (row.currency_code != data.currency_code or row.distance_unit != data.distance_unit):
        if db.scalar(select(CountryDeliverySettings.id).where(CountryDeliverySettings.country_code == row.country_code)):
            raise HTTPException(409, 'Currency and distance unit cannot change after pricing is configured')
    if row:
        configured = list(db.scalars(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == row.country_code)))
        if any(rule.service_fee_percent and not data.minimum_service_percent <= rule.service_fee_percent <= data.maximum_service_percent for rule in configured):
            raise HTTPException(409, 'Update existing service percentages before changing country limits')
    if not row:
        row = Country(country_code=data.country_code)
        db.add(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(AuditEvent(action='delivery-country-saved', target=data.country_code, details=data.model_dump_json()))
    db.flush()
    return row


def save_settings(db, code, data):
    country = db.scalar(select(Country).where(Country.country_code == code).with_for_update())
    if not country:
        raise HTTPException(404, 'Add country configuration first')
    if data.service_fee_percent and not country.minimum_service_percent <= data.service_fee_percent <= country.maximum_service_percent:
        raise HTTPException(422, f'Service fee must be zero or between {country.minimum_service_percent}% and {country.maximum_service_percent}%')
    row = db.scalar(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == code,
        CountryDeliverySettings.state == data.state, CountryDeliverySettings.city == data.city).with_for_update())
    if not row:
        row = CountryDeliverySettings(country_code=code, currency_code=country.currency_code)
        db.add(row)
    for key, value in data.model_dump(exclude={'distance_tiers'}).items():
        setattr(row, key, value)
    row.distance_tiers = json.dumps([tier.model_dump(mode='json') for tier in data.distance_tiers])
    db.add(AuditEvent(action='delivery-settings-saved', target=f'{code}:{data.state}:{data.city}', details=data.model_dump_json()))
    db.flush()
    return settings_view(row)


def save_surge(db, code, data, surge_id=None):
    if not db.scalar(select(Country.id).where(Country.country_code == code)):
        raise HTTPException(404, 'Country not found')
    row = db.get(DeliverySurgeRule, surge_id) if surge_id else DeliverySurgeRule(country_code=code)
    if not row or row.country_code != code:
        raise HTTPException(404, 'Surge rule not found')
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.add(AuditEvent(action='delivery-surge-saved', target=code, details=data.model_dump_json()))
    db.flush()
    return row


def delete_rule(db, model, rule_id):
    row = db.get(model, rule_id)
    if not row:
        raise HTTPException(404, 'Rule not found')
    if isinstance(row, CountryDeliverySettings) and not row.state and not row.city:
        raise HTTPException(409, 'Disable national pricing instead of deleting it')
    db.add(AuditEvent(action='delivery-rule-deleted', target=f'{model.__tablename__}:{rule_id}', details=row.country_code))
    db.delete(row)
    return {'deleted': rule_id}


def pricing(db, code, state='', city=''):
    country = db.scalar(select(Country).where(Country.country_code == code, Country.is_active.is_(True)))
    if not country:
        raise HTTPException(409, 'Delivery is not configured for this country')
    state, city = region(state), region(city)
    rows = list(db.scalars(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == code)))
    for target in ((state, city), (state, ''), ('', '')):
        row = next((row for row in rows if (row.state, row.city) == target), None)
        if row:
            if not row.active:
                raise HTTPException(409, 'Delivery pricing is disabled for this location')
            return country, row
    raise HTTPException(409, 'Configure delivery pricing for this country')


def distance_charge(distance, tiers):
    previous = Decimal(0)
    for tier in tiers:
        upper = Decimal(str(tier['up_to'])) if tier['up_to'] is not None else None
        if upper is None or distance <= upper:
            return money(Decimal(str(tier['fee'])) + max(Decimal(0), distance - previous) * Decimal(str(tier.get('per_unit', 0))))
        previous = upper
    raise HTTPException(409, 'Distance pricing is incomplete')


def compute(db, code, state, city, subtotal, distance_km, mode='delivery', discount=Decimal(0)):
    country, rule = pricing(db, code, state, city)
    km = Decimal(str(distance_km))
    if not km.is_finite() or km < 0:
        raise HTTPException(422, 'Invalid delivery distance')
    miles = km / Decimal('1.609344')
    distance = km if country.distance_unit == 'km' else miles
    base = rule.base_fee if mode == 'delivery' else Decimal(0)
    distance_fee = distance_charge(distance, json.loads(rule.distance_tiers)) if mode == 'delivery' else Decimal(0)
    small = rule.small_order_fee if mode == 'delivery' and subtotal < rule.small_order_threshold else Decimal(0)
    surge = Decimal(0)
    applied_surges = []
    if mode == 'delivery':
        timestamp = now()
        matching = list(db.scalars(select(DeliverySurgeRule).where(DeliverySurgeRule.country_code == code,
            DeliverySurgeRule.active.is_(True))))
        # Use the most specific rule for each reason, preventing country/city duplication.
        for reason in sorted({row.reason for row in matching}):
            candidates = [row for row in matching if row.reason == reason
                and (not row.state or row.state == region(state)) and (not row.city or row.city == region(city))
                and (not row.starts_at or row.starts_at <= timestamp) and (not row.ends_at or timestamp < row.ends_at)]
            if candidates:
                item = max(candidates, key=lambda row: (bool(row.city), bool(row.state), row.id))
                surge += item.amount
                applied_surges.append({'id': item.id, 'reason': item.reason, 'amount': str(item.amount)})
    free = mode == 'delivery' and rule.free_delivery_threshold is not None and subtotal >= rule.free_delivery_threshold and distance <= rule.free_delivery_max_distance
    delivery_discount = base + distance_fee if free else Decimal(0)
    delivery = money(base + distance_fee + small + surge - delivery_discount)
    service = money(subtotal * rule.service_fee_percent / 100)
    discount = min(subtotal, max(Decimal(0), money(discount)))
    total = money(subtotal + service + delivery - discount)
    return {'country_code': code, 'currency_code': country.currency_code, 'currency_symbol': country.currency_symbol,
        'state': region(state), 'city': region(city), 'distance_unit': country.distance_unit,
        'distance_km': km.quantize(Decimal('.0001')), 'distance_miles': miles.quantize(Decimal('.0001')),
        'food_total': money(subtotal), 'base_fee': money(base), 'distance_fee': money(distance_fee),
        'service_fee': service, 'surge_fee': money(surge), 'small_order_fee': money(small), 'discount': discount,
        'delivery_discount': money(delivery_discount), 'total_delivery_fee': delivery, 'grand_total': total,
        'free_delivery': free, 'pricing_rule_id': rule.id, 'surges': applied_surges,
        'settings_snapshot': json.dumps({'settings': settings_view(rule), 'surges': applied_surges}, default=str)}


def address_location(db, user, address_id):
    address = db.get(Address, address_id) if address_id else None
    if not address or address.customer_id != user.id:
        raise HTTPException(400, 'Choose a delivery address')
    if not address.country or address.latitude is None or address.longitude is None or not address.city:
        from backend.services.restaurant_location_service import geocode
        found = geocode(address=address.details)
        if found:
            for key in ('country', 'state', 'city', 'latitude', 'longitude'):
                if found.get(key) is not None:
                    setattr(address, key, found[key])
    return address


def quote(db, user, restaurant, subtotal, mode, address_id=None, discount=Decimal(0), tax=Decimal(0)):
    address = address_location(db, user, address_id) if mode == 'delivery' else None
    restaurant_country = normalize_country(restaurant.country)
    code = normalize_country(address.country) if address else restaurant_country
    code = code or restaurant_country
    if not code:
        raise HTTPException(409, 'Country is required for delivery pricing')
    if restaurant_country and code != restaurant_country:
        raise HTTPException(409, 'Restaurant and delivery address must be in the same country')
    km, source = Decimal(0), 'pickup'
    if address:
        from backend.services.eta_service import route
        origin = (restaurant.latitude, restaurant.longitude) if restaurant.latitude is not None and restaurant.longitude is not None else restaurant.address
        destination = (address.latitude, address.longitude) if address.latitude is not None and address.longitude is not None else address.details
        result = route(origin, destination)
        if result and result.get('distance_type') == 'driving':
            km, source = Decimal(str(result['distance_meters'])) / 1000, 'driving'
        elif isinstance(origin, tuple) and isinstance(destination, tuple):
            lat1, lat2 = math.radians(origin[0]), math.radians(destination[0])
            h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(destination[1]-origin[1])/2)**2
            km, source = Decimal(str(6371 * 2 * math.asin(math.sqrt(min(1, h))))), 'straight_line_estimate'
        else:
            raise HTTPException(409, 'Delivery distance unavailable. Confirm the address location or retry.')
    result = compute(db, code, address.state if address else '', address.city if address else '', subtotal, km, mode, discount)
    if result['currency_code'] != restaurant.currency:
        raise HTTPException(409, 'Restaurant currency does not match its country pricing')
    result['distance_source'] = source
    result['grand_total'] = money(result['grand_total'] + tax)
    return result


def snapshot(db, order, result):
    fields = ('country_code', 'currency_code', 'currency_symbol', 'state', 'city', 'distance_unit', 'distance_km',
        'distance_miles', 'distance_source', 'food_total', 'base_fee', 'distance_fee', 'service_fee', 'surge_fee',
        'small_order_fee', 'discount', 'total_delivery_fee', 'delivery_discount', 'settings_snapshot')
    row = OrderDeliveryFeeSnapshot(order_id=order.id, grand_total=order.total, **{key: result[key] for key in fields})
    db.add(row)
    return row


def public(result):
    return {'currency': result['currency_code'], 'symbol': result['currency_symbol'], 'foodTotal': result['food_total'],
        'deliveryFee': result['total_delivery_fee'], 'serviceFee': result['service_fee'], 'grandTotal': result['grand_total']}
