# GPS streaming on EC2

## Deploy

```bash
cd /home/krishna/food
sudo bash deploy/streaming/install.sh
```

The installer detects packages, verifies Redis/Kafka download checksums, preserves existing Kafka storage, creates six stream partitions, migrates the essential-points table, installs systemd units, enables boot startup, and configures HTTPS WebSocket proxying. Services listen on loopback; do not expose ports 6379, 9092, 9093, or 8002 in the EC2 security group.

```dotenv
GPS_STREAMING_ENABLED=true
GPS_REDIS_URL=redis://127.0.0.1:6379/2
GPS_KAFKA_BROKERS=127.0.0.1:9092
GPS_TTL_SECONDS=45
GPS_ALLOWED_ORIGINS=https://driver.dashvanti.com,https://customer.dashvanti.com,https://restaurant.dashvanti.com,https://admin.dashvanti.com
```

This deployment is a single-broker EC2 installation, not a highly available cluster. For multiple hosts, use private Redis/ElastiCache and Kafka/MSK endpoints, TLS and authentication, at least three brokers with replication factor three/minimum in-sync replicas two, and a load balancer supporting WebSockets. Each streaming instance joins `dashvanti-gps-fanout-v1`; Redis Pub/Sub distributes processed events to every instance's local WebSocket clients. Increase partitions before increasing consumers beyond six. Monitor connection counts, Kafka lag, Redis memory, CPU, and swap; load-test before increasing traffic.

## Service controls

```bash
sudo systemctl start redis-server kafka-server gps-streaming-service
sudo systemctl stop gps-streaming-service kafka-server redis-server
sudo systemctl restart gps-streaming-service
sudo systemctl restart redis-server kafka-server gps-streaming-service
sudo systemctl status redis-server kafka-server gps-streaming-service --no-pager
sudo systemctl enable redis-server kafka-server gps-streaming-service
```

## Monitoring

```bash
sudo journalctl -u redis-server -f
sudo journalctl -u kafka-server -f
sudo journalctl -u gps-streaming-service -f
curl --fail http://127.0.0.1:8002/health
/opt/dashvanti-redis/bin/redis-cli -n 2 INFO memory
KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-consumer-groups.sh --bootstrap-server 127.0.0.1:9092 --describe --group dashvanti-gps-fanout-v1
KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --describe --topic driver_location_stream
```

## Protocol

Authenticated clients obtain a scoped, fifteen-minute ticket from `POST /api/gps/ticket` with the existing JWT Authorization header. Customers and restaurants include `?order_id=123`; ownership and live status are checked. Administrators use `POST /api/gps/admin-ticket` with the existing server-side admin secret. Browser portals call their CSRF-protected `/customer/gps-ticket`, `/restaurant/gps-ticket`, `/driver/gps-ticket`, or `/admin/gps-ticket` endpoint; JWTs and admin secrets are not placed in HTML or WebSocket query strings.

Connect to one of:

```text
wss://driver.dashvanti.com/ws/driver/DRIVER_ID
wss://customer.dashvanti.com/ws/customer/ORDER_ID
wss://restaurant.dashvanti.com/ws/customer/ORDER_ID
wss://admin.dashvanti.com/ws/admin
```

First frame:

```json
{"ticket":"SCOPED_TICKET"}
```

Driver frame every four seconds, in degrees, metres/second, and metres:

```json
{"latitude":36.0821,"longitude":-86.7284,"heading":90,"speed":8,"accuracy":10}
```

The backend derives driver identity and active order from authenticated server data. Frames with invalid coordinates, low accuracy, expired sessions, offline drivers, or excessive frequency are rejected. Respond to `{"type":"ping"}` with `{"type":"pong"}`. Drivers receive `ready`, `ack`, `throttled`, and `error` messages. Viewers receive:

```json
{"type":"driver_location","driver_id":10,"order_id":123,"latitude":36.0821,"longitude":-86.7284,"heading":90,"speed":8,"accuracy":10,"timestamp":1790960000000,"event_id":"UUID","driver_name":"Driver","status":"PICKED_UP"}
```

Live coordinates and each driver's Geo key expire after 45 seconds without a GPS fix. Redis Geo sorted-set members do not individually support TTL; per-driver Geo keys have native expiry, and a five-second cleanup removes expired members from the shared Geo index. Offline drivers are removed immediately. Kafka retains events for six hours. Redis is a volatile live cache with disk persistence disabled.

Only `essential_gps_points` stores new GPS history: pickup, drop-off, route-start milestones, and route checkpoints at least 1 km and 120 seconds apart. Legacy GPS tables remain for existing records; with streaming enabled, neither the WebSocket nor compatibility REST GPS endpoint writes routine GPS rows to them. Existing order-status polling remains separate from push movement and preserves map interactions.

## Tests

```bash
cd /home/krishna/food
set -a
. ./.env
set +a
.venv/bin/python -m unittest discover -s tests -p test_gps_streaming.py -v
```

The integration test creates isolated zero-value orders and accounts, tests HTTPS WebSocket ingestion, customer/admin delivery through Kafka, throttling, identity isolation, sparse SQL milestones and real TTL expiry, then removes its fixtures. It uses approximately one minute and does not send real payments.

```bash
/opt/dashvanti-redis/bin/redis-cli -n 2 GEOSEARCH gps:drivers:geo FROMLONLAT -86.7284 36.0821 BYRADIUS 10 mi WITHDIST
/opt/dashvanti-redis/bin/redis-cli -n 2 GEOPOS gps:geo:DRIVER_ID DRIVER_ID
/opt/dashvanti-redis/bin/redis-cli -n 2 TTL gps:driver:DRIVER_ID
KAFKA_HEAP_OPTS='-Xms64m -Xmx128m' /opt/dashvanti-kafka/bin/kafka-console-consumer.sh --bootstrap-server 127.0.0.1:9092 --topic driver_location_stream --max-messages 3
```

Open the driver portal on HTTPS, go online, grant precise location permission, and keep it foreground. Open the same active order in the customer portal and the admin dashboard. Movement arrives by WebSocket without replacing the map. Browser GPS cannot reliably run after the phone locks or the browser is suspended; a native driver app must use an Android foreground location service with its required runtime permissions.

## Recovery

```bash
sudo systemctl restart gps-streaming-service
curl --fail http://127.0.0.1:8002/health
sudo journalctl -u gps-streaming-service -n 100 --no-pager
```

Kafka/Redis consumer connections and browser sockets reconnect automatically. Slow viewers have bounded queues and reconnect rather than blocking all clients. Historical orders cannot open live tracking. Kafka stale replays are discarded, events are keyed by driver, and Redis ignores out-of-order samples. Redis outages do not fall back to per-second PostgreSQL GPS writes.

Implementation references: [Redis GEOADD](https://redis.io/docs/latest/commands/geoadd/), [Redis EXPIRE](https://redis.io/docs/latest/commands/expire/), [Kafka KRaft](https://kafka.apache.org/41/operations/kraft/), [aiokafka producer](https://aiokafka.readthedocs.io/en/stable/producer.html).
# Live order broadcasts and navigation

```bash
cd /home/krishna/food
set -a; . ./.env; set +a
.venv/bin/python -m backend.migrate_order_stream
sudo systemctl restart gps-streaming-service dashvanti@api
sudo systemctl start redis-server gps-streaming-service
sudo systemctl stop gps-streaming-service
sudo systemctl restart redis-server gps-streaming-service
curl --fail http://127.0.0.1:8002/health
journalctl -u gps-streaming-service -u redis-server -f
PYTHONPATH=.:tests .venv/bin/python -m unittest tests/test_order_stream.py
```

Redis Pub/Sub and navigation run inside `gps-streaming-service`; they do not require additional systemd units. Existing Kafka GPS streaming remains enabled. Restart the four portal units after template changes:

```bash
sudo systemctl restart dashvanti@customer dashvanti@restaurant dashvanti@driver dashvanti@admin
```

Authenticated sockets: `/ws/customer/{order_id}`, `/ws/customer` (customer order feed), `/ws/driver/{driver_id}`, `/ws/driver/gps/{driver_id}` (GPS alias), `/ws/restaurant/{restaurant_id}`, `/ws/admin/orders` (`/ws/admin` remains compatible). Obtain a short-lived ticket through `POST /api/gps/ticket`; customer GPS subscriptions supply `order_id`. Admin tickets require the admin secret through `POST /api/gps/admin-ticket`. Send the ticket as the first WebSocket frame; URL tokens are not accepted. The Django portals obtain tickets using their authenticated session and CSRF protection.

Restaurant/driver updates use existing status endpoints or `POST /api/order/update`:

```json
{"order_id":123,"status":"PACKING"}
```

`READY`, `DELIVERING`, `COMPLETED` map to existing database states `READY_FOR_PICKUP`, `ON_THE_WAY_TO_CUSTOMER`, `DELIVERED`. Ownership and valid state transitions remain enforced; delivery transitions require the assigned driver. Orders and status history create transactional outbox records. Only committed transactions publish to `order_updates`; failed publications retry every second. Consumers deduplicate monotonically increasing event IDs. Five-second polling reconciles reconnect gaps without reloading pages or recreating maps.

```json
{"type":"order_update","order_id":123,"status":"PACKING","canonical_status":"PACKING","activity_status":"PACKING","timestamp":1791000000,"event_id":456}
```

GPS frames retain the four-second rate, Redis Geo TTL, Kafka fanout and essential database route points. GPS is pushed to the driver's own socket as well as authorized customer/admin sockets. Navigation resolves the current pickup/customer destination, caches real Directions API responses for 60 seconds, recomputes progress/ETA on GPS events, and reroutes after repeated off-route fixes. It never creates artificial road directions. Set `GOOGLE_MAPS_SERVER_API_KEY` to an IP-restricted server key with Directions API enabled; otherwise the existing `GOOGLE_MAPS_API_KEY` is attempted. Browser DirectionsService remains available when server directions are denied. Keep browser keys restricted to the portal domains and Maps JavaScript API. Required provider attribution remains visible.

The driver map uses a smooth car marker, vector heading rotation, centered follow mode, native street labels, street/instruction banner, remaining ETA/distance, route alternatives, automatic off-route rerouting, and Recenter after manual pan/zoom. Click **Start navigation in portal** to enable speech; mute/unmute lives on the map. Web Speech uses an installed English female voice (for example Samantha, Zira, Aria or Google UK English Female). If none is available, install a female English speech voice in device settings; the portal shows the requirement rather than silently selecting a different voice. Browser/OS voice availability and background GPS restrictions require testing on the actual device.

Test with a restaurant, assigned driver, customer and admin open simultaneously. Advance Accepted → Preparing → Packing → Ready; verify each table and tracking status updates without page reload. Advance driver pickup/delivery/completion; verify customer route changes to the delivery address, completion hides live tracking, and history stays map-free. On a real phone, start portal navigation, drive the route, test mute/unmute, pan/zoom then Recenter, deviate safely to verify rerouting, and compare live customer/admin movement. Restart the streaming service to verify reconnection preserves the map and input state. Never use test GPS as evidence of physical driving accuracy.

Provider references: [Directions API](https://developers.google.com/maps/documentation/directions/get-directions), [browser DirectionsService](https://developers.google.com/maps/documentation/javascript/legacy/directions), [device speech voices](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices).

