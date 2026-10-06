import time
import unittest
from unittest.mock import AsyncMock, patch
from backend.services import arrival_alert_service as arrival
from backend.services.websocket_manager import Peer, WebSocketManager


class Redis:
    def __init__(self): self.values = {}; self.messages = []
    async def get(self, key): return self.values.get(key)
    async def set(self, key, value, nx=False, **kwargs):
        if nx and key in self.values: return False
        self.values[key] = value; return True
    async def delete(self, key): self.values.pop(key, None)
    async def publish(self, channel, data): self.messages.append(data)
    async def mget(self, keys): return [self.values.get(key) for key in keys]


class ArrivalTests(unittest.IsolatedAsyncioTestCase):
    def event(self, **changes):
        return {'stage': 'customer', 'order_id': 11, 'driver_id': 22, 'customer_id': 33,
                'eta_seconds': 120, 'distance_meters': 400, 'accuracy': 10,
                'route_gap_meters': 0, 'timestamp': int(time.time() * 1000), **changes}

    async def test_thresholds_once_and_recent_replay(self):
        redis = Redis()
        with patch.object(arrival, '_owner', return_value=33), patch.object(arrival, '_orders', return_value=[(11, 22)]):
            self.assertTrue(await arrival.publish(redis, self.event()))
            self.assertFalse(await arrival.publish(redis, self.event()))
            self.assertEqual(len(redis.messages), 1)
            events = await arrival.pending(redis, 33, 11)
            self.assertEqual((events[0]['event'], events[0]['eta'], events[0]['distance']), ('driver_arriving', 2, 400))
        with patch.object(arrival, '_owner', return_value=33):
            self.assertTrue(await arrival.publish(Redis(), self.event(eta_seconds=121, distance_meters=300)))
            self.assertFalse(await arrival.publish(Redis(), self.event(eta_seconds=121, distance_meters=301)))

    async def test_pickup_invalid_stale_and_ineligible_are_silent(self):
        with patch.object(arrival, '_owner', return_value=33):
            for changes in [{'stage': 'restaurant'}, {'eta_seconds': float('nan')},
                            {'distance_meters': -1}, {'accuracy': 150}, {'route_gap_meters': 100},
                            {'timestamp': int(time.time() * 1000) - 20000}]:
                redis = Redis()
                self.assertFalse(await arrival.publish(redis, self.event(**changes)))
                self.assertEqual(redis.messages, [])
        with patch.object(arrival, '_owner', return_value=None):
            self.assertFalse(await arrival.publish(Redis(), self.event()))

    async def test_customer_audience_only(self):
        manager = WebSocketManager()
        peers = [Peer(None, scope, resource, {'sub': str(uid), 'role': role}) for scope, resource, uid, role in
                 [('order', 11, 33, 'customer'), ('customer', 33, 33, 'customer'),
                  ('customer', 44, 44, 'customer'), ('order', 11, 22, 'driver'),
                  ('driver', 22, 22, 'driver'), ('restaurant', 55, 55, 'restaurant'), ('admin', None, 0, 'admin')]]
        for peer in peers: manager.add(peer)
        data = {'type': 'driver_arriving', 'event': 'driver_arriving', 'order_id': 11, 'driver_id': 22, 'customer_id': 33}
        with patch('backend.services.gps_auth_service.visible_order', return_value=True):
            await manager.push(data)
        self.assertEqual([peer.queue.qsize() for peer in peers], [1, 1, 0, 0, 0, 0, 0])
        with patch('backend.services.gps_auth_service.visible_order', return_value=False):
            await manager.push(data)
        self.assertEqual(peers[0].queue.qsize(), 1)

    async def test_failed_broadcast_can_retry(self):
        redis = Redis(); redis.publish = AsyncMock(side_effect=RuntimeError('offline'))
        with patch.object(arrival, '_owner', return_value=33):
            with self.assertRaises(RuntimeError): await arrival.publish(redis, self.event())
            self.assertNotIn('arrival:sent:11:22', redis.values)


if __name__ == '__main__': unittest.main()
