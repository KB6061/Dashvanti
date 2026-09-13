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

