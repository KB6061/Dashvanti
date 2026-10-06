import json
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from backend.models import SystemConfig


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def terms(db, order):
    key = f'finance:terms:{order.id}'
    row = db.get(SystemConfig, key)
    if row:
        return json.loads(row.value)
    rule = db.get(SystemConfig, 'fund:restaurant_commission')
    cfg = json.loads(rule.value) if rule else {'method': 'percent', 'value': 15, 'enabled': True}
    result = {'method': cfg.get('method', 'percent'), 'value': str(cfg.get('value', 15)),
              'enabled': cfg.get('enabled', True)}
    db.execute(insert(SystemConfig).values(key=key,value=json.dumps(result)).on_conflict_do_nothing(index_elements=['key']))
    return json.loads(db.get(SystemConfig,key).value)


def breakdown(order, refund=0, cfg=None):
    total = money(order.total)
    tax = money(order.tax)
    service = money(order.service_fee)
    delivery = money(order.delivery_fee)
    tip = money(order.tip)
    food = money(max(total - tax - service - delivery - tip, 0))
    cfg = cfg or {'method': 'percent', 'value': 15, 'enabled': True}
    commission = money(min(food, food * Decimal(cfg['value']) / 100 if cfg['method'] == 'percent' else Decimal(cfg['value']))) if cfg['enabled'] else money(0)
    refund = money(min(max(money(refund), 0), total))
    ratio = (total - refund) / total if total else Decimal(0)
    restaurant = money((food - commission) * ratio)
    driver = money((delivery + tip) * ratio) if order.mode == 'delivery' and order.driver_id else money(0)
    tax_due = money(tax * ratio)
    driver = min(driver, money(max(total-refund-tax_due,0)))
    restaurant = min(restaurant, money(max(total-refund-tax_due-driver,0)))
    profit = money(total - refund - restaurant - driver - tax_due)
    return {'order_amount': total, 'food_amount': food, 'tax': tax_due,
            'service_fee': service, 'delivery_fee': delivery, 'tip': tip,
            'discount': money(order.discount), 'commission': money(commission * ratio),
            'driver_payout': driver, 'restaurant_payout': restaurant,
            'platform_profit': profit, 'refund_amount': refund, 'net_revenue': money(total-refund)}
