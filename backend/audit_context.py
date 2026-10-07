from contextvars import ContextVar

actor = ContextVar('dashvanti_audit_actor', default=None)
