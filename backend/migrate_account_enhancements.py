import inspect
from sqlalchemy import select,text
from backend.db import Base, engine, Session
from backend.models import SupportTicket, Review
from backend.customer_account_models import CustomerSupportReply
from backend.account_enhancement_models import Incident, IncidentMessage, ReviewPublication, GatewayControl
import backend.account_enhancement_models as models


def migrate():
    tables=[model.__table__ for _,model in inspect.getmembers(models,inspect.isclass) if model.__module__==models.__name__ and hasattr(model,'__table__')]
    Base.metadata.create_all(engine, tables=tables)
    if engine.dialect.name=='postgresql':
        with engine.begin() as connection:
            connection.execute(text("CREATE OR REPLACE FUNCTION protect_enterprise_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit records are immutable'; END; $$"))
            connection.execute(text('DROP TRIGGER IF EXISTS enterprise_audit_immutable ON enterprise_admin_audit'))
            connection.execute(text('CREATE TRIGGER enterprise_audit_immutable BEFORE UPDATE OR DELETE ON enterprise_admin_audit FOR EACH ROW EXECUTE FUNCTION protect_enterprise_audit()'))
    with Session() as db:
        from backend.models import SystemConfig,User
        from backend.account_enhancement_models import AdminPermission
        defaults={'Low':2880,'Medium':1440,'High':240,'Critical':60,'Emergency':15}
        for priority,minutes in defaults.items():
            key='support.sla_minutes.'+priority.lower()
            if not db.get(SystemConfig,key):db.add(SystemConfig(key=key,value=str(minutes)))
        owner=db.scalar(select(User).where(User.email=='system-admin@dashvanti.invalid',User.role=='admin'))
        if owner and not db.get(AdminPermission,owner.id):db.add(AdminPermission(user_id=owner.id,audit_rollback=True))
        db.flush()
        for ticket in db.scalars(select(SupportTicket)):
            from backend.services.incident_service import status
            ticket.status=status(ticket.status).lower().replace(' ','_')
            incident=db.get(Incident,ticket.id)
            if incident:
                if not incident.sla_due_at:
                    from datetime import timedelta
                    policy=db.get(SystemConfig,'support.sla_minutes.'+incident.priority.lower())
                    if policy:incident.sla_due_at=ticket.created_at+timedelta(minutes=int(policy.value))
                continue
            from datetime import timedelta
            db.add(Incident(ticket_id=ticket.id, category=ticket.subject, priority='Medium', department='Support',sla_due_at=ticket.created_at+timedelta(minutes=int(db.get(SystemConfig,'support.sla_minutes.medium').value))))
            for reply in db.scalars(select(CustomerSupportReply).where(CustomerSupportReply.ticket_id == ticket.id)):
                from backend.models import User
                author = db.get(User, reply.user_id)
                db.add(IncidentMessage(ticket_id=ticket.id, author_id=reply.user_id, author_role=author.role if author else 'customer', body=reply.body, created_at=reply.created_at))
            if ticket.resolution:
                db.add(IncidentMessage(ticket_id=ticket.id, author_id=None, author_role='admin', body=ticket.resolution, created_at=ticket.updated_at))
        for review in db.scalars(select(Review)):
            if not db.get(ReviewPublication, review.id):
                db.add(ReviewPublication(review_id=review.id, title='', status='pending'))
        from backend.services.account_gateway_service import GATEWAYS, INDIA_ONLY
        from backend.payment_models import PaymentMethod
        for name in GATEWAYS:
            if not db.get(GatewayControl, name):
                existing = db.get(PaymentMethod, 'phonepe') if name == 'phonepe' else None
                db.add(GatewayControl(name=name, enabled=bool(existing and existing.enabled), countries='IN' if name in INDIA_ONLY else 'US,IN'))
        db.commit()


if __name__ == '__main__':
    migrate()
