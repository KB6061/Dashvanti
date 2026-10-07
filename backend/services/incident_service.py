import csv
import io
import json
import re
import uuid
from datetime import timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func, or_, case
from backend.config import settings
from backend.models import User, Order, Restaurant, SupportTicket, SystemConfig, now
from backend.account_enhancement_models import Incident, IncidentMessage, IncidentAttachment, IncidentEvent, AdminPermission

STATUSES = ('Open', 'Assigned', 'In Progress', 'Waiting Customer', 'Escalated', 'Resolved', 'Closed')
PRIORITIES = ('Low', 'Medium', 'High', 'Critical', 'Emergency')


def number(ticket_id):
    return f'INC{ticket_id:010d}'


def status(value):
    return {'working': 'In Progress', 'open': 'Open'}.get(value, value.replace('_', ' ').title())


def permission(db, user, capability):
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator access required')
    grants = db.get(AdminPermission, user.id)
    if (capability == 'audit_rollback' and not grants) or (grants and not getattr(grants, capability)):
        raise HTTPException(403, 'Permission required: ' + capability)


def event(db, ticket, user, action, **details):
    db.add(IncidentEvent(ticket_id=ticket.id, actor_id=user.id, action=action, details=json.dumps(details)))
    ticket.updated_at = now()


def metadata(db, ticket):
    row = db.get(Incident, ticket.id)
    if not row:
        row = Incident(ticket_id=ticket.id, category=ticket.subject, priority='Medium', department='Support')
        db.add(row)
        db.flush()
    return row


def owned(db, user, ticket_id, lock=False):
    query = select(SupportTicket).where(SupportTicket.id == ticket_id)
    ticket = db.scalar(query.with_for_update() if lock else query)
    if not ticket or user.role != 'admin' and ticket.user_id != user.id:
        raise HTTPException(404, 'Ticket not found')
    return ticket


def public_ticket(db, ticket, user, thread=False):
    row = metadata(db, ticket)
    customer = db.get(User, ticket.user_id)
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    store = db.get(Restaurant, order.restaurant_id) if order else None
    result = {'id': ticket.id, 'number': number(ticket.id), 'customer_id': ticket.user_id,
              'customer_name': customer.name if customer else 'Deleted account', 'order_id': ticket.order_id,
              'restaurant': store.name if store else '', 'category': row.category, 'subcategory': row.subcategory,
              'priority': row.priority, 'status': status(ticket.status), 'description': ticket.description,
              'created_at': ticket.created_at, 'updated_at': ticket.updated_at, 'assigned_to': 'Support Team',
              'merged_into': number(row.merged_into_id) if row.merged_into_id else None}
    if user.role == 'admin':
        assignee = db.get(User, row.assignee_id) if row.assignee_id else None
        result.update(assignee_id=row.assignee_id, assignee=assignee.name if assignee else 'Unassigned',
                      department=row.department, sla_due_at=row.sla_due_at,
                      sla_breached=bool(row.sla_due_at and row.sla_due_at < now() and status(ticket.status) not in {'Resolved', 'Closed'}))
    if thread:
        query = select(IncidentMessage).where(IncidentMessage.ticket_id == ticket.id)
        attachments = select(IncidentAttachment).where(IncidentAttachment.ticket_id == ticket.id)
        if user.role != 'admin':
            query = query.where(IncidentMessage.internal == False)
            attachments = attachments.where(IncidentAttachment.internal == False)
        result['messages'] = []
        for message in db.scalars(query.order_by(IncidentMessage.id)):
            author = db.get(User, message.author_id) if message.author_id else None
            name = author.name if author else 'Deleted account'
            if user.role != 'admin' and message.author_role == 'admin':
                name = 'Support Team'
            result['messages'].append({'id': message.id, 'user': name, 'role': message.author_role,
                                       'body': message.body, 'internal': message.internal, 'created_at': message.created_at})
        result['attachments'] = [{'id': item.id, 'name': item.name, 'internal': item.internal,
                                  'created_at': item.created_at} for item in db.scalars(attachments.order_by(IncidentAttachment.id))]
        if user.role == 'admin':
            result['events'] = []
            for item in db.scalars(select(IncidentEvent).where(IncidentEvent.ticket_id == ticket.id).order_by(IncidentEvent.id)):
                author = db.get(User, item.actor_id) if item.actor_id else None
                result['events'].append({'action': item.action, 'actor': author.name if author else 'Deleted account',
                                         'details': json.loads(item.details), 'created_at': item.created_at})
    return result


def create(db, user, data):
    if not data.description.strip():
        raise HTTPException(422, 'Enter a description')
    if data.order_id:
        order = db.get(Order, data.order_id)
        field = {'customer': 'customer_id', 'restaurant': 'restaurant_id', 'driver': 'driver_id'}.get(user.role)
        if not order or user.role != 'admin' and (not field or getattr(order, field) != user.id):
            raise HTTPException(404, 'Order not found')
    ticket = SupportTicket(user_id=user.id, order_id=data.order_id, subject=data.category,
                           description=data.description.strip(), status='open')
    db.add(ticket)
    db.flush()
    row = metadata(db, ticket)
    row.category = data.category
    row.subcategory = data.subcategory
    row.priority = data.priority
    configured = db.get(SystemConfig, 'support.sla_minutes.' + data.priority.lower())
    if configured and configured.value.isdigit():
        row.sla_due_at = now() + timedelta(minutes=int(configured.value))
    event(db, ticket, user, 'created', priority=data.priority)
    return public_ticket(db, ticket, user, True)


def change(db, user, ticket_id, data):
    ticket = owned(db, user, ticket_id, True)
    row = metadata(db, ticket)
    if row.merged_into_id:
        raise HTTPException(409, 'Continue this conversation in ' + number(row.merged_into_id))
    if data.action != 'reply':
        permission(db, user, 'support_edit')
    if data.action in {'reply', 'note'}:
        if not data.body.strip():
            raise HTTPException(422, 'Enter a message')
        if user.role != 'admin' and status(ticket.status) == 'Closed':
            raise HTTPException(409, 'This ticket is closed. Create a new ticket for further assistance.')
        db.add(IncidentMessage(ticket_id=ticket.id, author_id=user.id, author_role=user.role,
                               body=data.body.strip(), internal=data.action == 'note'))
        if data.action == 'reply':
            ticket.status = 'waiting_customer' if user.role == 'admin' else 'open'
            if user.role == 'admin':
                ticket.resolution = data.body.strip()
    elif data.action == 'assign':
        assignee = db.get(User, data.assignee_id) if data.assignee_id else None
        if not assignee or assignee.role != 'admin':
            raise HTTPException(422, 'Choose an administrator or support agent')
        row.assignee_id = assignee.id
        row.department = data.department
        ticket.status = 'assigned'
    elif data.action == 'escalate':
        ticket.status = 'escalated'
        if data.priority:
            row.priority = data.priority
    elif data.action == 'status':
        if data.status not in STATUSES:
            raise HTTPException(422, 'Choose a ticket status')
        ticket.status = data.status.lower().replace(' ', '_')
        if data.priority:
            row.priority = data.priority
    elif data.action == 'merge':
        target = owned(db, user, data.merge_into, True)
        if target.id == ticket.id or target.user_id != ticket.user_id or metadata(db, target).merged_into_id:
            raise HTTPException(409, 'Merge into an unmerged ticket belonging to the same account')
        for model in (IncidentMessage, IncidentAttachment):
            for item in db.scalars(select(model).where(model.ticket_id == ticket.id)):
                item.ticket_id = target.id
        for item in db.scalars(select(IncidentEvent).where(IncidentEvent.ticket_id == ticket.id)):
            item.ticket_id = target.id
        db.add(IncidentMessage(ticket_id=target.id, author_id=user.id, author_role='admin',
                               body='Merged ' + number(ticket.id) + ': ' + ticket.description, internal=False))
        row.merged_into_id = target.id
        ticket.status = 'closed'
        event(db, target, user, 'merged_from', ticket=number(ticket.id))
    event(db, ticket, user, data.action, status=status(ticket.status), assignee_id=row.assignee_id,
          priority=row.priority, merged_into=row.merged_into_id)
    db.flush()
    return public_ticket(db, ticket, user, True)


def listing(db, user, q='', status_filter='', priority='', category='', assignee_id=None,
            date_from=None, date_to=None, sort='updated', direction='desc', page=1, size=25, customer_id=None):
    query = select(SupportTicket).outerjoin(Incident, Incident.ticket_id == SupportTicket.id)
    if user.role != 'admin':
        query = query.where(SupportTicket.user_id == user.id)
    elif customer_id:
        query = query.where(SupportTicket.user_id == customer_id)
    if q:
        value = q.strip()
        if re.fullmatch(r'INC\d+', value, re.I):
            query = query.where(SupportTicket.id == int(value[3:]))
        elif value.isdigit():
            query = query.where(or_(SupportTicket.id == int(value), SupportTicket.order_id == int(value)))
        else:
            match = '%' + value.replace('%', r'\%').replace('_', r'\_') + '%'
            people = select(User.id).where(or_(User.name.ilike(match, escape='\\'), User.email.ilike(match, escape='\\'), User.phone.ilike(match, escape='\\')))
            stores = select(Restaurant.id).where(Restaurant.name.ilike(match, escape='\\'))
            orders = select(Order.id).where(or_(Order.customer_id.in_(people), Order.restaurant_id.in_(stores), Order.driver_id.in_(people)))
            query = query.where(or_(SupportTicket.subject.ilike(match, escape='\\'), SupportTicket.description.ilike(match, escape='\\'), SupportTicket.user_id.in_(people), SupportTicket.order_id.in_(orders)))
    if status_filter:
        query = query.where(SupportTicket.status == status_filter.lower().replace(' ', '_'))
    if priority:
        query = query.where(Incident.priority == priority)
    if category:
        query = query.where(Incident.category == category)
    if assignee_id:
        query = query.where(Incident.assignee_id == assignee_id)
    if date_from:
        query = query.where(SupportTicket.created_at >= date_from)
    if date_to:
        query = query.where(SupportTicket.created_at < date_to + timedelta(days=1))
    columns = {'updated': SupportTicket.updated_at, 'created': SupportTicket.created_at,
               'number': SupportTicket.id, 'status': SupportTicket.status,
               'priority': case({'Low':1,'Medium':2,'High':3,'Critical':4,'Emergency':5}, value=Incident.priority, else_=2)}
    column = columns.get(sort, SupportTicket.updated_at)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(column.asc() if direction == 'asc' else column.desc(), SupportTicket.id.desc()).offset((page-1)*size).limit(size))
    return {'total': total, 'page': page, 'size': size, 'items': [public_ticket(db, row, user) for row in rows]}


def csv_export(items):
    stream = io.StringIO(newline='')
    fields = ('number', 'customer_name', 'order_id', 'restaurant', 'category', 'priority', 'status', 'created_at')
    writer = csv.writer(stream)
    writer.writerow(fields)
    for item in items:
        values = [str(item.get(key) or '') for key in fields]
        writer.writerow(["'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value for value in values])
    return stream.getvalue()


def upload(db, user, ticket_id, file, internal=False):
    ticket=owned(db, user, ticket_id)
    if internal:
        permission(db, user, 'support_edit')
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, 'Choose a file up to 5 MB')
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 30000000:
                raise ValueError()
            output = io.BytesIO()
            ImageOps.exif_transpose(image).convert('RGB').save(output, 'JPEG', quality=85)
            raw, mime, suffix = output.getvalue(), 'image/jpeg', '.jpg'
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        if raw.startswith(b'%PDF-') and file.content_type == 'application/pdf':
            mime, suffix = 'application/pdf', '.pdf'
        else:
            raise HTTPException(422, 'Attachments must be JPEG, PNG, WebP or PDF')
    directory = Path(settings.file_root) / 'support' / str(ticket_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + suffix)
    path.write_bytes(raw)
    path.chmod(0o640)
    row = IncidentAttachment(ticket_id=ticket_id, author_id=user.id, internal=internal, path=str(path),
                             name=Path(file.filename or 'attachment').name[:150], mime=mime)
    db.add(row)
    db.info.setdefault('incident_uploads', []).append(path)
    event(db,ticket,user,'attachment_added',internal=internal,name=row.name)
    db.flush()
    return {'id': row.id, 'name': row.name}


def attachment(db, user, attachment_id):
    row = db.get(IncidentAttachment, attachment_id)
    if not row or row.internal and user.role != 'admin':
        raise HTTPException(404, 'Attachment not found')
    owned(db, user, row.ticket_id)
    path = Path(row.path).resolve()
    if not path.is_relative_to(Path(settings.file_root).resolve()) or not path.is_file():
        raise HTTPException(404, 'Attachment not found')
    return row, path
