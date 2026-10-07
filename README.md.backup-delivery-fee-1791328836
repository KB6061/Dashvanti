# Dashvanti Food Delivery System

Django portals → internal FastAPI REST API → Oracle. A transactional Oracle outbox feeds Kafka and SMTP. Uploads are normalized JPEG files under `/opt/dashvanti_fs/{customers,restaurants,drivers}/{user_id}/`; metadata stays in Oracle. Django stores JWTs in server-side sessions and contains no business persistence.

## Local deployment

1. Install Docker Engine with Compose (Linux containers; Oracle needs adequate memory).
2. Run `python setup_env.py` to generate `.env` with unique local secrets (already generated for this workspace). The Compose DB_PASSWORD and DATABASE_URL password must match.
3. Run `docker compose up --build -d`.
4. Visit http://localhost:8000. Development reset emails appear at http://localhost:8025.
5. Register one account in each portal. In the restaurant dashboard, save the address and enable Open; add menu items. Customers add an address, browse, add items and checkout. Restaurants confirm → prepare → ready. Online drivers accept a ready order and advance delivery statuses.

Orders use cash on delivery/pickup. Delivery costs ₹30, credited as driver earnings; restaurant revenue excludes this fee. Pickup is completed by the restaurant. Opening hours are informational; the Open switch is the authoritative availability setting. Driver assignment is first-accept from a ready-order queue, with row locking and one active delivery per driver.

## Structure

- `backend/routers`: REST endpoints and role dependencies.
- `backend/services`: authentication, users, restaurants, menus, orders, deliveries, files and event handling.
- `backend/models.py`: Oracle-compatible SQLAlchemy schema, including all requested tables plus users, carts, password resets and outbox.
- `backend/schemas.py`: validated request models.
- `backend/worker.py`: retrying Kafka/email publisher. Events are at least once; consumers must deduplicate by event ID.
- `frontend/{customer,restaurant,driver}_app`: separate routes, views, forms and templates.
- `frontend/common_app`: API client and shared session/portal views.
- `deploy/nginx.conf`: public gateway, upload limit and auth rate limit.
- `tests`: API workflow and security regression tests.

## API and routes

OpenAPI is available at the internal API `/docs` and `/openapi.json`. Do not expose the API directly without rate limiting and TLS. All business endpoints use `/api`.

| Area | Endpoints |
|---|---|
| Auth | POST `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/forgot`, `/auth/reset` |
| Profiles | GET/PUT `/me`; GET/POST `/addresses`; PUT/DELETE `/addresses/{id}` |
| Catalog | GET `/restaurants`, `/restaurants/{id}`; PUT `/restaurant/profile`; GET/POST `/menu`; PUT/DELETE `/menu/{id}` |
| Orders | GET/PUT `/cart`; GET/POST `/orders`; GET `/orders/{id}`; POST `/orders/{id}/status`, `/reorder`, `/review` |
| Delivery | GET `/delivery/available`; PUT `/delivery/availability`; POST `/delivery/{id}/accept` |
| Reporting | GET `/stats?period=daily|weekly|monthly` |
| Files | GET/POST `/files`; GET `/files/{id}` |

Customer pages: `/customer/login`, `/register`, `/forgot`, `/reset`, `/restaurants`, `/restaurant/{id}`, `/cart`, `/checkout`, `/addresses`, `/orders`, `/order/{id}/track`, `/profile`, `/files` (all under `/customer`). Restaurant pages use `/restaurant/` with `dashboard`, `menu`, `orders`, `order/{id}`, `stats`. Driver pages use `/driver/` with `dashboard`, `orders`, `order/{id}`, `earnings`. Each role has authentication, profile and upload pages.

## Database and migrations

`python -m backend.migrate` creates the initial schema. `python -m backend.migrate --sql` prints Oracle DDL. This bootstrap is not an upgrade migration system: version and review explicit ALTER migrations before changing a deployed schema. SQLAlchemy binds query values; no user values are interpolated into SQL. Order creation serializes each customer's cart and uses a unique idempotency key. Status updates and driver acceptance lock order rows.

## Verification

Install `requirements.txt` in a Python 3.12 virtual environment; run `python -m pytest -q`. Unit/integration tests use SQLite for fast API logic checks. Oracle lock semantics, Kafka availability, SMTP and Docker deployment must additionally be tested on the target stack. Run `python frontend/manage.py check` with environment variables set. See `VERIFICATION.md` for checks actually performed. `schema.sql` and `openapi.json` contain generated Oracle DDL and the complete REST contract. `requirements.lock.txt` records the locally tested dependency versions.

## Production deployment requirements

This repository is an implementation for staging validation, not a claim of audited production readiness. Before public launch:

- Lock and audit resolved dependencies; pin deployment images by digest. Current version ranges permit compatible security updates.
- Configure trusted HTTPS ingress, `COOKIE_SECURE=true`, actual `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, private API networking and a secret manager. Never keep example database credentials.
- Use managed/backed-up Oracle with a least-privilege runtime account separate from the schema migration user; test restore procedures and schema upgrades.
- Configure replicated Kafka with TLS/SASL. The supplied single broker is for local staging; monitor unpublished outbox age and worker failures. Retain/purge published outbox rows under your retention policy. Reset-link outbox payloads contain short-lived secrets until successfully mailed; restrict database access and backups accordingly.
- Configure a verified SMTP sender and TLS. Mailpit is development-only. Failed sends retry; reset messages can be duplicated after a crash.
- Back up uploads; use a private, quota-controlled filesystem and review retention. Document uploads accept images only and are private to their owner. Add document verification/approval policy and malware scanning before relying on regulatory documents operationally.
- Shared file sessions support the supplied single web container; use a shared production session backend for multi-host deployment and schedule `clearsessions`.
- Run Oracle concurrency/load tests, accessibility/browser checks and an end-to-end deployment exercise. Add monitoring, alerting and operational support procedures.

Catalog responses cap at 100 restaurants, lists at 200 orders, and reviews at 50. Add cursor pagination for larger deployments. Reports are rolling 1/7/30-day windows by order creation time. No payment gateway, geolocation/maps, refunds or automated regulatory approval are claimed. Menu deletion disables items to preserve order history.


## AWS Nginx and HTTPS setup applied on 13.234.22.13

Current production host:

- Server: AWS EC2, Elastic IP `13.234.22.13`
- Project path: `/home/krishna/food`
- Service control script: `/home/krishna/food/script/dashvanti-services.sh`
- Nginx config: `/etc/nginx/conf.d/dashvanti.conf`
- Certbot path: `/opt/certbot/bin/certbot`
- Auto-renew cron: `/etc/cron.d/certbot-renew`
- PostgreSQL: `127.0.0.1:5432`, database `dashvanti`

Public portals:

| Portal | Public URL | Local upstream |
|---|---|---|
| Customer | `https://customer.dashvanti.com` | `http://127.0.0.1:8080` |
| Restaurant | `https://restaurant.dashvanti.com` | `http://127.0.0.1:8081` |
| Driver | `https://driver.dashvanti.com` | `http://127.0.0.1:8082` |
| Admin | `https://admin.dashvanti.com` | `http://127.0.0.1:8083` |

DNS records in GoDaddy:

```text
customer.dashvanti.com   A   13.234.22.13
restaurant.dashvanti.com A   13.234.22.13
driver.dashvanti.com     A   13.234.22.13
admin.dashvanti.com      A   13.234.22.13
```

What was installed/configured:

- Installed Nginx with `dnf install -y nginx`.
- Installed Certbot in isolated Python venv at `/opt/certbot`.
- Created Nginx reverse proxy config in `/etc/nginx/conf.d/dashvanti.conf`.
- Enabled Nginx on boot with `systemctl enable --now nginx`.
- Opened AWS security group ports `80` and `443`; both already existed when verified.
- Issued Let's Encrypt certificate for all four subdomains.
- Added automatic renewal cron with reload hook.
- Fixed SELinux for Nginx reverse proxy:

```bash
sudo semanage port -m -t http_port_t -p tcp 8080
sudo semanage port -m -t http_port_t -p tcp 8081
sudo semanage port -m -t http_port_t -p tcp 8082
sudo semanage port -m -t http_port_t -p tcp 8083
sudo setsebool -P httpd_can_network_connect 1
```

- Updated `/home/krishna/food/.env` for HTTPS domains:

```text
ALLOWED_HOSTS=*,13.234.22.13,customer.dashvanti.com,restaurant.dashvanti.com,driver.dashvanti.com,admin.dashvanti.com,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://customer.dashvanti.com,https://restaurant.dashvanti.com,https://driver.dashvanti.com,https://admin.dashvanti.com,http://13.234.22.13:8080,http://13.234.22.13:8081,http://13.234.22.13:8082,http://13.234.22.13:8083,http://127.0.0.1:8080,http://127.0.0.1:8081,http://127.0.0.1:8082,http://127.0.0.1:8083
PUBLIC_URL=https://customer.dashvanti.com
CUSTOMER_URL=https://customer.dashvanti.com
RESTAURANT_URL=https://restaurant.dashvanti.com
DRIVER_URL=https://driver.dashvanti.com
ADMIN_URL=https://admin.dashvanti.com
```

Common operations:

```bash
cd /home/krishna/food
./script/dashvanti-services.sh start all
./script/dashvanti-services.sh stop all
./script/dashvanti-services.sh status all
sudo systemctl restart nginx
sudo /opt/certbot/bin/certbot renew --dry-run
```

Verification performed:

```bash
curl -ksI https://customer.dashvanti.com/ | head -1
curl -ksI https://restaurant.dashvanti.com/ | head -1
curl -ksI https://driver.dashvanti.com/ | head -1
curl -ksI https://admin.dashvanti.com/ | head -1
```

Expected response is `HTTP/1.1 302 Found`, which means Nginx and Django are connected correctly.


## Real-time GPS streaming on AWS EC2

Service controls and boot startup: [operations guide](deploy/systemd/CONTROL.md).

```bash
sudo dashvanti start
sudo dashvanti stop
sudo dashvanti restart
dashvanti status
sudo dashvanti restart web
sudo dashvanti restart api
sudo dashvanti restart gps
```

```bash
cd /home/krishna/food
sudo bash deploy/streaming/install.sh
sudo systemctl start redis-server kafka-server gps-streaming-service
sudo systemctl stop gps-streaming-service kafka-server redis-server
sudo systemctl restart gps-streaming-service
sudo journalctl -u gps-streaming-service -f
curl --fail http://127.0.0.1:8002/health
set -a; . ./.env; set +a
.venv/bin/python -m unittest discover -s tests -p test_gps_streaming.py -v
```

See [deployment, service controls, monitoring, protocol, tests, and scaling](deploy/streaming/README.md).
Driver GPS sends every four seconds through authenticated WebSockets; Redis Geo holds expiring live locations, Kafka `driver_location_stream` delivers events, and customer/admin maps consume push updates. PostgreSQL stores essential route points and delivery milestones only.

Order statuses also broadcast through Redis `order_updates` after database commit, with a transactional retry outbox. Customer, driver, restaurant and admin portals update without page reload. The existing streaming service provides driver route guidance, street/instruction updates, heading-aware centered car movement, ETA/distance, route rerouting and female Web Speech voice with a map mute control. See [order broadcast and navigation setup](deploy/streaming/README.md).

```bash
cd /home/krishna/food
set -a; . ./.env; set +a
.venv/bin/python -m backend.migrate_order_stream
sudo systemctl restart gps-streaming-service dashvanti@api
.venv/bin/python -m unittest discover -s tests -p test_order_stream.py -v
```

## Arrival sound

- Original CC0 chime: `/sounds/arrival.mp3` (0.85 seconds).
- Customer-only `driver_arriving` events trigger at ETA <= 2 minutes OR remaining route distance <= 300 meters, after pickup.
- Accurate, fresh, on-route GPS is required. Each delivery/driver alerts once; reconnects replay recent events without repeating the sound.
- Arrival sound defaults on. Website and Android mute settings persist. Web browsers require an initial interaction to permit audio; blocked playback exposes an Enable arrival sound button.
- Android plays its packaged `res/raw/arrival.mp3` while the authenticated app is foregrounded. Closed/background app delivery requires a separate push notification integration.

```bash
cd /home/krishna/food
set -a; . ./.env; set +a
.venv/bin/python -m unittest tests.test_arrival_alerts -v
sudo dashvanti restart gps
sudo dashvanti restart customer
curl -fsS -o /dev/null https://customer.dashvanti.com/sounds/arrival.mp3
sudo journalctl -u gps-streaming-service -f
```

```json
{"event":"driver_arriving","order_id":123,"driver_id":45,"eta":1.5,"distance":250,"timestamp":1790000000000}
```

Connect using a short-lived authenticated ticket from `POST /api/gps/ticket` and send `{"ticket":"..."}` as the first WebSocket frame to `/ws/customer` or `/ws/customer/{order_id}`. Tokens and order ownership are verified by the backend. Never put credentials in WebSocket URLs.

Android: build with JDK 17, Gradle 8.9 and Android SDK 35: `gradle :app:assembleDebug`. Install the generated APK and sign in to test the local chime and switch on an actual phone.


## Driver Partner Management (India)

Driver onboarding: https://driver.dashvanti.com/driver/partner
Admin: https://admin.dashvanti.com/admin/driver-partners
Operations managers: /admin/driver-partners/manager-login (a provisioned users.role=operations_manager account; public registration cannot create staff accounts).

New driver accounts start in DRAFT. Upload all ten private image documents, then submit for admin review. Documents are encrypted on disk; bank/profile data is encrypted in PostgreSQL. Full Aadhaar numbers are not retained: duplicate checks use an HMAC and displays retain only the final four digits. Keep PAYMENT_ENCRYPTION_KEY and optional DRIVER_IDENTITY_HASH_KEY backed up and stable. Upload masked Aadhaar images. The verification report checks submitted formats/expiry and records manual review; it does not claim UIDAI authentication.

Existing drivers remain compatible until enrolled in the module. Newly registered drivers require approval, unexpired approved documents and a verified production security deposit before going online. Bike/scooter: INR 1,000; car: INR 3,000. PhonePe credentials and environment are configured in Admin Payments. Sandbox deposit payments are labelled SANDBOX_PAID and cannot activate a production driver. Payment callbacks and status checks verify the provider response; redirects never mark a deposit paid.

Offers expire after 30 seconds and pass to the next eligible online driver. Existing Redis GPS, 10 driving-mile eligibility, live maps and upcoming-order queue remain in use. GPS samples remain in Redis/Kafka; this module does not restore per-second database writes. Delivery OTP is generated after pickup, shown only to the owning customer and required for enrolled drivers to finish delivery. It has a 24-hour expiry and five failed-attempt limit. Completion credits earnings once. Withdrawals reserve the same per-order payout ledger used by Admin Funds, preventing duplicate payouts; bank/UPI transfers are recorded only after an admin enters an actual confirmation number. Existing Stripe Connect payouts remain available for supported USD orders. This module does not claim PhonePe UPI payouts: PhonePe PG is used for deposits and refunds, not bank disbursement.

Insurance amounts are proposed benefits until an admin records an issued policy. Claim records track insurer references and outcomes; they do not purchase insurance or submit claims to an insurer API. SOS creates an incident, shows an admin alert and queues contact notifications. Emergency delivery depends on configured providers; the driver page includes a direct 112 call link.

Optional notification environment variables (never commit credentials):
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
SMTP_HOST, SMTP_PORT=587, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
GOOGLE_APPLICATION_CREDENTIALS=/secure/path/firebase-service-account.json
DRIVER_FIREBASE_WEB_CONFIG='{"apiKey":"PUBLIC_KEY","authDomain":"PROJECT.firebaseapp.com","projectId":"PROJECT","messagingSenderId":"SENDER","appId":"APP_ID"}'
DRIVER_FIREBASE_VAPID_KEY=PUBLIC_VAPID_KEY

Enable browser push from Driver Partner > Enable push notifications. Android/other driver clients can register their FCM token using POST /api/driver/partner/devices with an authenticated driver JWT and {"installation_id":"stable-installation-id","token":"FCM_TOKEN"}; remove it using DELETE /api/driver/partner/devices/{installation_id}. Notification queues remain PENDING when provider configuration is absent and are marked SENT only after provider success. Firebase project/authorized domains and valid service credentials are required for background push.

```bash
sudo systemctl enable --now dashvanti-driver-partners.service
sudo systemctl start dashvanti-driver-partners.service
sudo systemctl stop dashvanti-driver-partners.service
sudo systemctl restart dashvanti-driver-partners.service
sudo journalctl -u dashvanti-driver-partners.service -f
cd /home/krishna/food
set -a; source .env; set +a
PYTHONPATH=. .venv/bin/python deploy/migrate_driver_partners.py
.venv/bin/python -m unittest backend.tests.test_driver_partners -v
```

Admin reports: active, online, daily-deliveries, earnings, ratings, deposits, withdrawals, incidents, suspensions, insurance-claims. JSON downloads are available through each report page. Admin/operations-manager access is enforced on the backend. Managers can review documents, approve, reject and suspend; only admins can deactivate/reactivate, reveal bank details, process refunds/withdrawals or configure insurance.
