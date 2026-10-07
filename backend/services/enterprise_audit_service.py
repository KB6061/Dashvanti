import json
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import event, inspect, select, func
from sqlalchemy.orm import Session as ORMSession
from fastapi import HTTPException
from backend.db import Base
from backend.models import User, now
from backend.account_enhancement_models import EnterpriseAudit

SENSITIVE = ('password', 'secret', 'token', 'credential', 'cvv', 'pan', 'bank_account', 'routing', 'account_number')
BOOKKEEPING={'updated_at','moderated_at','moderator_id','created_at'}
ROLLBACK_FIELDS = {
    'restaurants': {'name', 'description', 'cuisine', 'kind', 'is_open', 'opening', 'closing', 'delivery_minutes'},
    'menu_items': {'name', 'description', 'category', 'price', 'veg', 'available'},
    'customer_profiles': {'language', 'state', 'city', 'timezone', 'theme'},
    'account_gateway_controls': {'enabled', 'countries'},
    'support_incidents': {'priority', 'assignee_id', 'department'},
    'review_publications': {'status'},
    'country_delivery_settings': {'base_fee','small_order_threshold','small_order_fee','free_delivery_threshold','free_delivery_max_distance','service_fee_percent','active','distance_tiers','state','city','per_extra_distance','extra_distance_start'},
    'delivery_surge_rules': {'amount','active','country_code','state','city','reason','starts_at','ends_at'},
    'entity_verifications': {'verified','evidence','verified_by'},
}


def encode(value):
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return '[binary]'
    return value


def safe(data):
    result = {key: '[redacted]' if any(word in key.lower() for word in SENSITIVE) else encode(value)
              for key, value in data.items()}
    if any(word in str(data.get('key','')).lower() for word in SENSITIVE) and 'value' in result:
        result['value']='[redacted]'
    if 'payload' in result and any(word in str(result['payload']).lower() for word in ('secret','token')):
        result['payload']='[redacted]'
    return result


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=encode)


def record(db, actor, action, module, key, old, new, reason='', status='success', rollback_of=None):
    db.add(EnterpriseAudit(actor_id=actor.get('id'), actor_name=actor.get('name', ''), role=actor.get('role', 'admin'),
                           action=action, module=module, entity_key=dumps(key), old_value=dumps(safe(old)),
                           new_value=dumps(safe(new)), reason=reason[:500], ip_address=actor.get('ip', '')[:80],
                           device=actor.get('device', '')[:500], status=status, rollback_of_id=rollback_of))


def install():
    if getattr(install, 'ready', False):
        return
    install.ready = True

    @event.listens_for(ORMSession, 'after_begin')
    def inherit_actor(db,transaction,connection):
        from backend.audit_context import actor
        identity=actor.get()
        if identity and 'audit_actor' not in db.info:
            db.info['audit_actor']=identity
            db.info['audit_reason']=identity.get('reason','')

    @event.listens_for(ORMSession, 'before_flush')
    def before_flush(db, context, instances):
        from backend.audit_context import actor as actor_context
        identity=actor_context.get()
        if identity and 'audit_actor' not in db.info:
            db.info['audit_actor']=identity
            db.info['audit_reason']=identity.get('reason','')
        from backend.models import Review, SupportTicket
        db.info.setdefault('account_new_records', []).extend(obj for obj in db.new if isinstance(obj,(Review,SupportTicket)))
        actor = db.info.get('audit_actor')
        for obj in db.dirty | db.deleted:
            if isinstance(obj, EnterpriseAudit):
                raise HTTPException(409, 'Audit records are immutable')
        if not actor or actor.get('role') != 'admin':
            return
        pending = db.info.setdefault('audit_pending', [])
        for obj in db.new | db.dirty | db.deleted:
            if isinstance(obj, EnterpriseAudit) or obj in db.dirty and not db.is_modified(obj):
                continue
            mapper = inspect(type(obj))
            table = mapper.local_table
            key = {column.key: getattr(obj, mapper.get_property_by_column(column).key) for column in table.primary_key}
            old = {}
            if obj not in db.new:
                condition = [column == key[column.key] for column in table.primary_key]
                row = db.connection().execute(select(table).where(*condition)).mappings().first()
                old = dict(row) if row else {}
            pending.append((obj, table, old, 'delete' if obj in db.deleted else 'create' if obj in db.new else 'update'))

    @event.listens_for(ORMSession, 'after_flush_postexec')
    def after_flush(db, context):
        from backend.models import Review, SupportTicket
        from backend.account_enhancement_models import ReviewPublication, Incident
        for obj in db.info.pop('account_new_records',[]):
            if isinstance(obj,Review) and not db.get(ReviewPublication,obj.id):
                db.add(ReviewPublication(review_id=obj.id,status='pending'))
            if isinstance(obj,SupportTicket) and not db.get(Incident,obj.id):
                db.add(Incident(ticket_id=obj.id,category=obj.subject,priority='Medium',department='Support'))
        pending = db.info.pop('audit_pending', [])
        actor = db.info.get('audit_actor', {})
        for obj, table, old, action in pending:
            mapper = inspect(type(obj))
            new = {} if action == 'delete' else {column.key: getattr(obj, mapper.get_property_by_column(column).key) for column in table.c}
            key = {column.key: getattr(obj, mapper.get_property_by_column(column).key) for column in table.primary_key}
            record(db, actor, action, table.name, key, old, new, db.info.get('audit_reason', ''))

    @event.listens_for(ORMSession, 'do_orm_execute', retval=True)
    def bulk_execute(state):
        if not (state.is_update or state.is_delete):
            return state.invoke_statement()
        table = state.statement.table
        if table.name == EnterpriseAudit.__tablename__:
            raise HTTPException(409, 'Audit records are immutable')
        from backend.audit_context import actor as actor_context
        identity=actor_context.get()
        if identity and 'audit_actor' not in state.session.info:state.session.info['audit_actor']=identity
        actor = state.session.info.get('audit_actor')
        if not actor or actor.get('role') != 'admin':
            return state.invoke_statement()
        condition = list(state.statement._where_criteria)
        old_rows = state.session.connection().execute(select(table).where(*condition), state.parameters or {}).mappings().all()
        result = state.invoke_statement()
        for old in old_rows:
            key = {column.key: old[column.key] for column in table.primary_key}
            new = {}
            if state.is_update:
                row = state.session.connection().execute(select(table).where(*(column == key[column.key] for column in table.primary_key))).mappings().first()
                new = dict(row) if row else {}
            record(state.session, actor, 'delete' if state.is_delete else 'update', table.name, key, dict(old), new, state.session.info.get('audit_reason', ''))
        return result

    @event.listens_for(ORMSession, 'after_rollback')
    def rollback_files(db):
        db.info.pop('audit_pending', None)
        db.info.pop('account_new_records', None)
        for path in db.info.pop('incident_uploads', []):
            path.unlink(missing_ok=True)

    @event.listens_for(ORMSession, 'after_commit')
    def committed_files(db):
        db.info.pop('incident_uploads', None)


def listing(db, q='', admin_id=None, module='', action='', status='', date_from=None, date_to=None, page=1, size=25):
    query = select(EnterpriseAudit)
    if q:
        term = '%' + q.replace('%', r'\%').replace('_', r'\_') + '%'
        query = query.where(EnterpriseAudit.actor_name.ilike(term, escape='\\') | EnterpriseAudit.reason.ilike(term, escape='\\') | EnterpriseAudit.entity_key.ilike(term, escape='\\'))
    for column, value in ((EnterpriseAudit.actor_id, admin_id), (EnterpriseAudit.module, module), (EnterpriseAudit.action, action), (EnterpriseAudit.status, status)):
        if value:
            query = query.where(column == value)
    if date_from:
        query = query.where(EnterpriseAudit.created_at >= date_from)
    if date_to:
        from datetime import timedelta
        query = query.where(EnterpriseAudit.created_at < date_to + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(EnterpriseAudit.id.desc()).offset((page-1)*size).limit(size))
    return {'total': total, 'page': page, 'size': size, 'items': [detail(row) for row in rows]}


def detail(row):
    result = {key: getattr(row, key) for key in ('id', 'actor_id', 'actor_name', 'role', 'action', 'module', 'reason', 'ip_address', 'device', 'status', 'created_at', 'rollback_of_id')}
    result.update(key=json.loads(row.entity_key), old=json.loads(row.old_value), new=json.loads(row.new_value))
    result['differences'] = [{'field': key, 'old': result['old'].get(key), 'new': result['new'].get(key)}
                             for key in sorted(result['old'].keys() | result['new'].keys()) if result['old'].get(key) != result['new'].get(key)]
    allowed = ROLLBACK_FIELDS.get(row.module, set())
    changed=[item for item in result['differences'] if item['field'] not in BOOKKEEPING]
    result['rollback_available'] = row.action == 'update' and bool(changed) and all(item['field'] in allowed for item in changed)
    return result


def rollback(db, user, audit_id, reason):
    from backend.services.incident_service import permission
    permission(db, user, 'audit_rollback')
    row = db.scalar(select(EnterpriseAudit).where(EnterpriseAudit.id == audit_id).with_for_update())
    if not row:
        raise HTTPException(404, 'Audit record not found')
    data = detail(row)
    if not data['rollback_available']:
        raise HTTPException(409, 'This action cannot be rolled back. Deletions, payments and credentials require their dedicated workflows.')
    mapper = next((mapper for mapper in Base.registry.mappers if mapper.local_table.name == row.module), None)
    if not mapper:
        raise HTTPException(409, 'Module is unavailable')
    model = mapper.class_
    conditions = [getattr(model, mapper.get_property_by_column(column).key) == data['key'][column.key] for column in mapper.primary_key]
    target = db.scalar(select(model).where(*conditions).with_for_update())
    if not target:
        raise HTTPException(409, 'The record no longer exists')
    for item in data['differences']:
        column = mapper.local_table.c[item['field']]
        field = mapper.get_property_by_column(column).key
        if encode(getattr(target, field)) != item['new']:
            raise HTTPException(409, 'The record changed since this audit. Review the latest version first.')
    for item in data['differences']:
        if item['field'] in BOOKKEEPING:continue
        column = mapper.local_table.c[item['field']]
        value = item['old']
        if value is not None:
            python_type = column.type.python_type
            if python_type in (datetime, date):
                value = python_type.fromisoformat(value)
            elif python_type is Decimal:
                value = Decimal(value)
        setattr(target, mapper.get_property_by_column(column).key, value)
    db.info['audit_reason'] = reason
    db.flush()
    restored={column.key:getattr(target,mapper.get_property_by_column(column).key) for column in mapper.local_table.c}
    record(db, db.info.get('audit_actor', {'id': user.id, 'name': user.name, 'role': user.role}), 'rollback', row.module, data['key'], data['new'], restored, reason, rollback_of=row.id)
    return {'message': 'Previous values restored', 'audit_id': row.id}
