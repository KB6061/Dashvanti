import json
import uuid
from backend.models import Outbox

def emit(db, event_type, payload):
    db.add(Outbox(event_id=str(uuid.uuid4()), event_type=event_type, payload=json.dumps(payload)))
