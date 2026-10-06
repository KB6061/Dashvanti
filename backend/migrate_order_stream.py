import backend.models
from sqlalchemy import inspect, text
from backend.models_order_stream import OrderBroadcastEvent
from backend.db import engine

if __name__ == '__main__':
    OrderBroadcastEvent.__table__.create(engine, checkfirst=True)
    if not inspect(engine).get_foreign_keys('order_broadcast_events'):
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM order_broadcast_events WHERE NOT EXISTS (SELECT 1 FROM orders WHERE orders.id=order_broadcast_events.order_id)'))
            connection.execute(text('ALTER TABLE order_broadcast_events ADD CONSTRAINT fk_order_broadcast_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE'))
