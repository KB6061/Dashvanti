import json
import logging
import smtplib
import time
from email.message import EmailMessage
from confluent_kafka import Producer
from sqlalchemy import select
from backend.config import settings
from backend.db import Session
from backend.models import Outbox

logging.basicConfig(level=logging.INFO)

def send_mail(payload):
    message = EmailMessage()
    message['From'] = settings.smtp_from
    message['To'] = payload['email']
    message['Subject'] = 'Reset your Dashvanti password'
    message.set_content('Reset your password within 30 minutes: ' + payload['url'])
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)

def run():
    producer = Producer({'bootstrap.servers':settings.kafka_bootstrap_servers, 'enable.idempotence':True, 'acks':'all', 'delivery.timeout.ms':15000})
    while True:
        try:
            with Session.begin() as db:
                # Lock one pending row; skip rows being handled by another worker.
                row = next(iter(db.scalars(select(Outbox).where(Outbox.published == False).order_by(Outbox.id).with_for_update(skip_locked=True)).yield_per(1)), None)
                if row:
                    payload = json.loads(row.payload)
                    if row.event_type == 'MAIL_PASSWORD_RESET':
                        send_mail(payload)
                        row.payload = '{}'
                    else:
                        errors = []
                        producer.produce('dashvanti.events', key=str(payload.get('order_id', payload.get('user_id',''))), value=json.dumps({'id':row.event_id,'type':row.event_type,'data':payload,'created_at':row.created_at.isoformat()}), on_delivery=lambda error, message: errors.append(error) if error else None)
                        if producer.flush(20) or errors:
                            raise RuntimeError('Kafka delivery failed')
                    row.published = True
            if not row:
                time.sleep(1)
        except Exception:
            logging.exception('Outbox delivery failed; will retry')
            time.sleep(5)

if __name__ == '__main__':
    run()
