from io import BytesIO
from pathlib import Path
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal
from xml.sax.saxutils import escape
from fastapi import HTTPException
from sqlalchemy import select, func
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
from backend.models import Order, DeliveryStatus, now
from backend.services.order_service import detail

def local_time(value, tz):
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, 'Invalid time zone')
    if value is None:
        return 'Not recorded'
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).strftime('%b %d, %Y %I:%M %p %Z')

def money(value):
    return f'${Decimal(value or 0):,.2f}'

def pdf(title, notes, rows):
    output = BytesIO()
    width, margin = 80 * mm, 4 * mm
    content_width = width - 2 * margin
    body = ParagraphStyle('Receipt', fontSize=8, leading=11)
    heading = ParagraphStyle('Heading', fontSize=10, leading=13, alignment=1)
    paragraph = lambda value: Paragraph(escape(str(value)), body)
    logo = Image(str(Path(__file__).resolve().parents[2] / 'frontend/logo/logo.jpeg'))
    ratio = min(90 / logo.imageWidth, 55 / logo.imageHeight)
    logo.drawWidth, logo.drawHeight = logo.imageWidth * ratio, logo.imageHeight * ratio
    story = [logo, Spacer(1, 6), Paragraph(escape(title), heading), Spacer(1, 8)]
    story.extend(paragraph(note) for note in notes if note)
    story.append(Spacer(1, 8))
    for row in rows[1:]:
        label = escape(str(row[0]))
        if len(row) == 4 and row[1] != '':
            label += '<br/>' + escape(str(row[1])) + ' x ' + escape(str(row[2]))
        elif len(row) == 5:
            label += '<br/>' + escape(str(row[1]))
            if row[2] != '':
                label += '<br/>Delivery fee: ' + escape(str(row[2])) + ' / Tip: ' + escape(str(row[3]))
        table = Table([[Paragraph(label, body), paragraph(row[-1])]],
                      colWidths=[content_width * .70, content_width * .30])
        table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LINEBELOW', (0,0), (-1,-1), .3, colors.lightgrey),
        ]))
        story.append(table)
    measured = [(item, *item.wrap(content_width, 14000)) for item in story]
    height = min(14400, max(80 * mm, sum(h for _, _, h in measured) + 2 * margin))
    canvas = Canvas(output, pagesize=(width, height))
    canvas.setTitle(title)
    canvas.setAuthor('Dashvanti')
    y = height - margin
    for item, item_width, item_height in measured:
        if y - item_height < margin:
            canvas.showPage()
            y = height - margin
        item.drawOn(canvas, (width - item_width) / 2, y - item_height)
        y -= item_height
    canvas.save()
    return output.getvalue()

def bill(db, user, order_id, tz="America/Chicago"):
    data = detail(db, user, order_id)
    order = data['order']
    items = data['items']
    delivered = max((event.created_at for event in data['history'] if event.status == 'DELIVERED'), default=None)
    delivery_time = local_time(delivered, tz) if order.status == 'DELIVERED' else 'Not delivered yet'
    rows = [['Item / charge', 'Quantity', 'Unit price', 'Amount']]
    rows.extend([[item.name, item.quantity, money(item.price), money(item.price * item.quantity)] for item in items])
    subtotal = sum((item.price * item.quantity for item in items), Decimal('0'))
    charges = [('Subtotal', subtotal), ('Tax', order.tax), ('Service fee', order.service_fee),
               ('Delivery fee', order.delivery_fee), ('Discount', -(order.discount or 0)),
               ('Delivery Partner tip', order.tip), ('Total', order.total)]
    rows.extend([[name, '', '', money(value)] for name, value in charges])
    return pdf(f'Dashvanti - Order #{order.id} bill', [
        data['restaurant']['name'], data['restaurant']['address'] or '',
        'Customer: ' + (data['customer'] or {}).get('name', ''),
        f'Order date: {local_time(order.created_at, tz)}',
        f'Delivery date and time: {delivery_time}',
        f'Status: {order.status} | {order.mode}',
        order.address or '', 'Order bill - not confirmation of payment.',
    ], rows)

def earnings(db, user, period, tz="America/Chicago"):
    days = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period)
    if not days:
        raise HTTPException(400, 'Invalid period')
    end = now()
    start = end - timedelta(days=days)
    orders = db.scalars(select(Order).where(
        Order.driver_id == user.id, Order.status == 'DELIVERED',
        Order.created_at >= start, Order.created_at <= end
    ).order_by(Order.created_at)).all()
    delivered = dict(db.execute(select(DeliveryStatus.order_id, func.max(DeliveryStatus.created_at))
        .join(Order, Order.id == DeliveryStatus.order_id)
        .where(Order.driver_id == user.id, Order.status == 'DELIVERED',
               Order.created_at >= start, Order.created_at <= end, DeliveryStatus.status == 'DELIVERED')
        .group_by(DeliveryStatus.order_id)).all())
    rows = [['Order', 'Order / delivery date', 'Delivery fee', 'Tip', 'Earnings']]
    total = Decimal('0')
    for order in orders:
        amount = (order.delivery_fee or 0) + (order.tip or 0)
        total += amount
        rows.append([str(order.id), 'Ordered: ' + local_time(order.created_at, tz) + ' / Delivered: ' + local_time(delivered.get(order.id), tz),
                     money(order.delivery_fee), money(order.tip), money(amount)])
    rows.append(['Total', str(len(orders)) + ' completed orders', '', '', money(total)])
    return pdf('Dashvanti - Delivery Partner earnings', [
        user.name, f'Rolling {period}: {local_time(start, tz)} to {local_time(end, tz)}',
        'Completed orders filtered by order date, matching portal earnings.',
        'Earnings include delivery fees and tips; this is not a payout receipt.',
    ], rows)
