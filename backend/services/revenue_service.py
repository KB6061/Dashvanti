import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import and_, select

from backend.models import AuditEvent, Order, OrderItem, PayoutTransaction, Restaurant, SystemConfig, User, now

from backend.services.finance_service import breakdown, terms

CENT = Decimal('0.01')
FINAL_STATUSES = {'DELIVERED', 'COMPLETED'}
REPORT_TIMEZONE = ZoneInfo(os.environ.get('BUSINESS_TIMEZONE','America/Chicago'))


def money(value):
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def percent(value):
    return Decimal(str(value or 0)) / Decimal('100')


def _start_of_week(day):
    return day - timedelta(days=day.weekday())


def date_window(range_name='', start='', end=''):
    today=datetime.now(REPORT_TIMEZONE).date()
    first,last=date(1970,1,1),date(2999,12,31)
    try:
        if start or end:
            first=date.fromisoformat(start) if start else first
            last=date.fromisoformat(end) if end else last
        elif range_name=='today':first=last=today
        elif range_name=='week':first=_start_of_week(today);last=first+timedelta(days=6)
        elif range_name=='month':
            first=today.replace(day=1)
            following=first.replace(year=first.year+1,month=1) if first.month==12 else first.replace(month=first.month+1)
            last=following-timedelta(days=1)
        elif range_name=='year':first=today.replace(month=1,day=1);last=today.replace(month=12,day=31)
    except ValueError as exc:
        raise HTTPException(422,'Invalid report date') from exc
    if first>last:raise HTTPException(422,'Start date must be before end date')
    def utc(day,end=False):
        return datetime.combine(day,datetime.max.time() if end else datetime.min.time(),REPORT_TIMEZONE).astimezone(timezone.utc).replace(tzinfo=None)
    return utc(first),utc(last,True)


def _config(db, key, default):
    row = db.get(SystemConfig, key)
    if not row:
        return Decimal(default)
    try:
        data = json.loads(row.value)
        if data.get('enabled') is False:
            return Decimal(default)
        return Decimal(str(data.get('value', default)))
    except Exception:
        return Decimal(default)


def commission_rate(db):
    return percent(_config(db, 'fund:restaurant_commission', '15'))


def driver_payout_amount(order):
    if order.mode != 'delivery' or not order.driver_id:
        return Decimal('0.00')
    return money(order.delivery_fee + order.tip)


def refund_map(db):
    rows = db.scalars(select(SystemConfig).where(SystemConfig.key.like('refund:%')))
    refunds = {}
    for row in rows:
        try:
            data = json.loads(row.value)
            order_id = int(data.get('order_id'))
            refunds[order_id] = refunds.get(order_id, Decimal('0.00')) + money(data.get('amount'))
        except Exception:
            continue
    return refunds


def payout_map(db):
    rows = db.scalars(select(PayoutTransaction))
    paid = {}
    for row in rows:
        if row.status not in {'PAID','TRANSFERRED'}:
            continue
        paid[(row.order_id, row.payee_role)] = paid.get((row.order_id, row.payee_role), Decimal('0.00')) + money(row.amount)
    return paid


def row_amounts(order, refund_amount, rate):
    values=breakdown(order,refund_amount,{'method':'percent','value':str(rate*100),'enabled':True})
    return tuple(values[key] for key in ('order_amount','commission','driver_payout','restaurant_payout','platform_profit'))


def _period_key(dt, period):
    dt=dt.replace(tzinfo=timezone.utc).astimezone(REPORT_TIMEZONE)
    if period == 'day':
        return dt.strftime('%Y-%m-%d')
    if period == 'week':
        first = _start_of_week(dt.date())
        return first.strftime('%Y-W%U')
    if period == 'month':
        return dt.strftime('%Y-%m')
    if period == 'year':
        return dt.strftime('%Y')
    return f'Order -{dt}'


def _add_bucket(target, key, profit, driver, restaurant, refund):
    row = target.setdefault(key, {'period': key, 'platform_profit': Decimal('0'), 'driver_payout': Decimal('0'), 'restaurant_payout': Decimal('0'), 'refund_amount': Decimal('0'), 'orders': 0})
    row['platform_profit'] += profit
    row['driver_payout'] += driver
    row['restaurant_payout'] += restaurant
    row['refund_amount'] += refund
    row['orders'] += 1


def revenue_report(db, filters):
    start_dt, end_dt = date_window(filters.get('date_range', ''), filters.get('start_date', ''), filters.get('end_date', ''))
    stmt = select(Order).where(Order.currency == 'USD', Order.status.not_in(['PAYMENT_PENDING', 'PAYMENT_FAILED', 'SANDBOX_PAID']), and_(Order.created_at >= start_dt, Order.created_at <= end_dt)).order_by(Order.id.desc())
    if filters.get('restaurant_id'):
        stmt = stmt.where(Order.restaurant_id == int(filters['restaurant_id']))
    if filters.get('driver_id'):
        stmt = stmt.where(Order.driver_id == int(filters['driver_id']))
    if filters.get('status'):
        stmt = stmt.where(Order.status == filters['status'])
    if filters.get('payment_mode'):
        stmt = stmt.where(Order.payment_mode == filters['payment_mode'])
    orders = list(db.scalars(stmt))
    users = {row.id: row for row in db.scalars(select(User))}
    restaurants = {row.id: row for row in db.scalars(select(Restaurant))}
    refunds = refund_map(db)
    paid = payout_map(db)
    reserved = dict(paid)
    processing = {}
    for payout in db.scalars(select(PayoutTransaction).where(PayoutTransaction.status.in_(['PENDING','UNKNOWN','REVIEW_REQUIRED']))):
        key=(payout.order_id,payout.payee_role)
        reserved[key]=reserved.get(key,Decimal(0))+money(payout.amount)
        processing[key]=payout.status
    item_names = {}
    if orders:
        for item in db.scalars(select(OrderItem).where(OrderItem.order_id.in_([order.id for order in orders]))):
            item_names.setdefault(item.order_id, []).append(item.name)
    rate = commission_rate(db)
    query = (filters.get('q') or '').casefold()
    rows = []
    totals = {'order_amount': Decimal('0'), 'platform_profit': Decimal('0'), 'commission': Decimal('0'), 'driver_payout': Decimal('0'), 'restaurant_payout': Decimal('0'), 'refund_amount': Decimal('0'), 'tax': Decimal('0'), 'service_fee': Decimal('0'), 'delivery_fee': Decimal('0'), 'tip': Decimal('0'), 'discount': Decimal('0'), 'net_revenue': Decimal('0')}
    completed_count = 0
    buckets = {'day': {}, 'week': {}, 'month': {}, 'year': {}}
    commission_history = {}
    for order in orders:
        restaurant = restaurants.get(order.restaurant_id)
        customer = users.get(order.customer_id)
        driver = users.get(order.driver_id) if order.driver_id else None
        refund_amount = money(refunds.get(order.id, 0))
        values = breakdown(order, refund_amount, terms(db,order))
        order_amount, commission, driver_payout, restaurant_payout, platform_profit = (values[key] for key in ('order_amount','commission','driver_payout','restaurant_payout','platform_profit'))
        haystack = f'{order.id} {restaurant.name if restaurant else ""} {customer.name if customer else ""} {driver.name if driver else ""} {order.payment_mode} {order.status} {" ".join(item_names.get(order.id, []))}'.casefold()
        if query and query not in haystack:
            continue
        if order.status in FINAL_STATUSES:
            completed_count += 1
            for key in totals:
                totals[key] += values[key]
            for period in buckets:
                _add_bucket(buckets[period], _period_key(order.created_at, period), platform_profit, driver_payout, restaurant_payout, refund_amount)
            rest_key = order.restaurant_id
            history = commission_history.setdefault(rest_key, {'restaurant_id': rest_key, 'restaurant_name': restaurant.name if restaurant else f'Restaurant #{rest_key}', 'commission': Decimal('0'), 'orders': 0})
            history['commission'] += commission
            history['orders'] += 1
        rows.append({
            'order_id': order.id,
            'customer_name': customer.name if customer else 'Unknown',
            'restaurant_name': restaurant.name if restaurant else 'Unknown',
            'driver_name': driver.name if driver else 'Unassigned',
            **values,
            'order_amount': order_amount,
            'platform_commission': commission,
            'driver_payout': driver_payout,
            'restaurant_payout': restaurant_payout,
            'refund_amount': refund_amount,
            'platform_profit': platform_profit,
            'payment_mode': order.payment_mode or 'Card',
            'order_status': order.status,
            'timestamp': order.created_at.isoformat(sep=' ', timespec='minutes'),
            'driver_remaining': money(max(driver_payout-reserved.get((order.id,'driver'),0),0)),
            'restaurant_remaining': money(max(restaurant_payout-reserved.get((order.id,'restaurant'),0),0)),
            'driver_paid': money(paid.get((order.id, 'driver'), 0)),
            'restaurant_paid': money(paid.get((order.id, 'restaurant'), 0)),
            'driver_payment_status': processing.get((order.id,'driver')) or ('PAID' if paid.get((order.id, 'driver'), 0) >= driver_payout and driver_payout > 0 else ('PENDING ADMIN PAY' if order.driver_id and order.status in FINAL_STATUSES and driver_payout > 0 else 'NOT READY')),
            'restaurant_payment_status': processing.get((order.id,'restaurant')) or ('PAID' if paid.get((order.id, 'restaurant'), 0) >= restaurant_payout and restaurant_payout > 0 else ('PENDING ADMIN PAY' if order.status in FINAL_STATUSES and restaurant_payout > 0 else 'NOT READY')),
            'can_quick_pay_driver': bool(order.driver_id and order.status in FINAL_STATUSES and reserved.get((order.id, 'driver'), 0) < driver_payout),
            'can_quick_pay_restaurant': bool(order.status in FINAL_STATUSES and reserved.get((order.id, 'restaurant'), 0) < restaurant_payout),
        })
    total_for_chart = totals['platform_profit'] + totals['driver_payout'] + totals['restaurant_payout'] + totals['refund_amount'] + totals['tax']
    chart = [{
        'name': name,
        'amount': money(value),
        'percent': money((value / total_for_chart * 100) if total_for_chart else 0),
    } for name, value in [('Platform revenue', totals['platform_profit']), ('Driver payouts', totals['driver_payout']), ('Restaurant payouts', totals['restaurant_payout']), ('Refunds reserved', totals['refund_amount']), ('Tax payable', totals['tax'])]]
    return {
        'rows': rows,
        'completed_orders': completed_count,
        'report_timezone': str(REPORT_TIMEZONE),
        'totals': {key: money(value) for key, value in totals.items()},
        'summary_cards': summary_cards(db),
        'chart': chart,
        'buckets': {key: [dict(row, platform_profit=money(row['platform_profit']), driver_payout=money(row['driver_payout']), restaurant_payout=money(row['restaurant_payout']), refund_amount=money(row['refund_amount'])) for row in values.values()] for key, values in buckets.items()},
        'commission_history': [dict(row, commission=money(row['commission'])) for row in commission_history.values()],
        'restaurants': [{'id': r.id, 'name': r.name} for r in restaurants.values()],
        'drivers': [{'id': u.id, 'name': u.name} for u in users.values() if u.role == 'driver'],
        'statuses': sorted({row['order_status'] for row in rows}),
        'payment_modes': sorted({row['payment_mode'] for row in rows}),
        'quick_pay_history': quick_pay_history(db),
    }


def _profit_for_orders(db, range_name):
    report = revenue_report(db, {'date_range': range_name}) if range_name else revenue_report(db, {})
    return report['totals']['platform_profit']


def summary_cards(db):
    orders=list(db.scalars(select(Order).where(Order.currency=='USD',Order.status.in_(FINAL_STATUSES))))
    def total_for(range_name):
        start,end=date_window(range_name)
        return money(sum((order.total for order in orders if start <= order.created_at <= end), Decimal(0)))
    return {key:total_for(period) for key,period in [('today','today'),('week','week'),('month','month'),('year','year'),('lifetime','')]}


def quick_pay_history(db):
    users = {row.id: row for row in db.scalars(select(User))}
    rows = []
    for row in db.scalars(select(PayoutTransaction).order_by(PayoutTransaction.id.desc()).limit(200)):
        payee = users.get(row.payee_id)
        from backend.services.payout_service import receipt
        details=receipt(db,row)
        rows.append({**details, 'id': row.id, 'order_id': row.order_id, 'payee_role': row.payee_role, 'payee_name': payee.name if payee else f'User #{row.payee_id}', 'amount': money(row.amount), 'status': row.status, 'method': row.method, 'reference': row.reference, 'created_at': row.created_at, 'paid_at': row.paid_at})
    return rows


def quick_pay(db, order_id, payee_role):
    raise HTTPException(422, 'Use the payout form with amount, mode and bank confirmation')


EXPORT_FIELDS = ['order_id','customer_name','restaurant_name','driver_name','order_amount','platform_commission','driver_payout','restaurant_payout','refund_amount','payment_mode','order_status','timestamp']


def export_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=EXPORT_FIELDS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def export_pdf(rows):
    lines = ['Dashvanti Revenue Report', 'OrderID  Customer  Restaurant  Driver  Amount  Commission  DriverPay  RestaurantPay  Refund  Payment  Status  Timestamp']
    for row in rows[:500]:
        lines.append('  '.join(str(row.get(key, '')) for key in EXPORT_FIELDS))
    text = []
    y = 760
    for line in lines:
        safe = str(line)[:150].replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        text.append(f'BT /F1 8 Tf 36 {y} Td ({safe}) Tj ET')
        y -= 12
        if y < 36:
            break
    stream = '\n'.join(text).encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(pdf)
