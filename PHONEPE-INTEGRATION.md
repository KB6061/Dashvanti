# Dashvanti PhonePe payments

The integration runs in the existing FastAPI API and Django customer/admin portals. Every API path below is prefixed with `/api` on the deployed site. Sandbox is the initial mode; gateway methods start disabled.

The AWS project is already updated. For another checkout of this same project, copy the new source files from the archive and apply `integration.patch` to the existing files with `git apply integration.patch`. Review the diff before applying it to a different project revision. The archive contains new modules plus a focused patch; it does not replace unrelated existing files.

## Configure sandbox

1. Obtain **PhonePe PG** sandbox credentials from PhonePe Developer Settings. A PhonePe Business/UPI account by itself is not a PG API credential. Current Standard Checkout uses client ID, client secret and client version. See [PhonePe authorization](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/authorization).
2. Open `https://admin.dashvanti.com/admin/payments` and sign in with the existing admin account.
3. Select **Sandbox / Standard Checkout v2**. Enter client credentials and a webhook username/password; save. The API-key field is stored as a merchant reference, not substituted for a v2 client secret.
4. In the PhonePe dashboard, configure a **SHA** webhook at `https://customer.dashvanti.com/api/phonepe/callback` using that username/password. Subscribe to payment-completed/failed and refund-completed/failed events. See [PhonePe webhook setup](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/webhook).
5. Enable PhonePe in admin. It is still unavailable until the required credentials are complete.
6. Set the customer's profile country to `India` or `IN`. Existing customer profiles also expose `PUT /api/payment/country`. Alternatively configure `GEOIP_DATABASE_PATH` with a MaxMind country MMDB; unknown locations fail closed. No external geolocation request is made.
7. Use a dedicated test restaurant with **INR** prices. Admin → Payments can set its billing currency after explicit price/fee confirmation. This does **not** convert dollar menu prices or global fee rules. Existing restaurants/orders remain USD.
8. Add its meals to the cart. PhonePe appears only for an eligible Indian customer with an INR cart. Payment opens PhonePe's hosted UPI/intent/QR checkout. Test in a desktop browser and an Android browser using the PhonePe sandbox instructions. Sandbox success records `SANDBOX_PAID` and does not notify restaurants or dispatch drivers.

## Backend files

```
backend/
  payment_models/{payment,refund,admin_settings}.py
  payment_schemas.py
  services/{phonepe_service,admin_payment_service,geo_service}.py
  utils/{signature,payment_security}.py
  routers/{phonepe,admin_payment}.py
  migrate_payments.py
  reconcile_payments.py
```

`User.country`, `Restaurant.currency`, and `Order.currency` extend existing `backend/models.py`. The new models live in `payment_models` to preserve existing model imports. Router, service and model remain separate.

## Environment

See `phonepe.env.example`. Credentials may be seeded from `PHONEPE_CLIENT_ID`, `PHONEPE_CLIENT_SECRET`, `PHONEPE_CLIENT_VERSION`, `PHONEPE_WEBHOOK_USERNAME` and `PHONEPE_WEBHOOK_PASSWORD`. Legacy fields are `PHONEPE_MERCHANT_ID`, `PHONEPE_SALT_KEY`, `PHONEPE_SALT_INDEX`, `PHONEPE_API_KEY`.

`PAYMENT_ENCRYPTION_KEY` is a Fernet key; `PAYMENT_PROXY_SECRET` signs client IP information forwarded internally by Django. The deployment generates both once. Back up the encryption key alongside database backups; replacing it prevents decrypting saved credentials. Do not put either key in browser code. Admin updates create immutable credential versions so older transactions/refunds remain associated with their original merchant and environment.

The current API uses OAuth `O-Bearer`. Legacy v1 implements base64 JSON and `SHA256(base64_payload + api_path + salt_key).hexdigest() + "###" + salt_index` as `X-VERIFY`. Legacy callbacks sign the encoded response without an API path. Use legacy mode only for a merchant explicitly provisioned for v1; it is not the default for new accounts. Modern hosted checkout configures `UPI_INTENT`/`UPI_QR` through payment-mode configuration. See [PhonePe create payment](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/create-payment).

## Customer API examples

Send the normal Dashvanti JWT as `Authorization: Bearer <JWT>`. Amounts are derived from the server cart and fee rules; the customer cannot submit an arbitrary charge amount.

```http
GET /api/payment/methods
```
```json
{"country":"IN","methods":[{"id":"cash","name":"Cash on delivery / pickup"},{"id":"phonepe","name":"PhonePe / UPI","currency":"INR","environment":"sandbox"}]}
```
Non-Indian, unknown-country, disabled or unconfigured cases contain cash only. The backend enforces India eligibility on payment creation even if a customer modifies HTML. Profile country is user-declared location, not proof of nationality; IP lookup is used when profile country is absent. Untrusted `CF-IPCountry` or country headers are never accepted.

```http
PUT /api/payment/country
```
```json
{"country":"India"}
```
```http
POST /api/phonepe/pay
```
```json
{"checkout":{"mode":"pickup","address_id":null,"request_key":"unique_checkout_request_123456","tip":"0","promo_code":null},"instrument":"UPI"}
```
`instrument` also accepts `UPI_INTENT` or `REDIRECT`. Use the returned `redirect_url` to open hosted checkout. The same customer/request key returns the same transaction without another charge. Multi-restaurant carts are aggregated only when currencies match. Payment amounts and refunds are integer paisa: INR 1 = 100 paisa.

```http
POST /api/phonepe/status
```
```json
{"transaction_id":123}
```
Only the owning customer may query it. `GET /api/phonepe/transaction/123` returns the local transaction/checkout link. `POST /api/phonepe/callback` accepts authenticated PhonePe webhooks. Customer browser redirects never mark an order paid. A callback is durably logged and triggers a server-to-server status check; completion requires matching the stored order reference and exact amount. Production completion releases pending orders once.

## Admin APIs

All admin routes use the existing backend `admin_secret` dependency. The Django admin portal requires an authenticated server-side admin session and CSRF for mutations; it supplies `X-Dashvanti-Admin-Secret` internally. Never expose this header value to customer JavaScript. Ordinary customer JWTs cannot access admin routes or issue refunds.

| Method | API |
| --- | --- |
| GET | `/api/admin/payment/settings` |
| POST | `/api/admin/payment/settings/update` |
| POST | `/api/admin/payment/methods/toggle` |
| GET | `/api/admin/payment/transactions?offset=0&limit=25&status=PENDING` |
| GET | `/api/admin/payment/transaction/123` |
| POST | `/api/admin/payment/transaction/123/status` |
| POST | `/api/admin/payment/refund/123` |
| POST | `/api/admin/payment/refund/456/status` (refund ID) |
| GET | `/api/admin/payment/settlements` |
| POST | `/api/admin/payment/settlements/import` |
| GET | `/api/admin/payment/logs` |
| POST | `/api/admin/payment/restaurant-currency` |

`POST /api/phonepe/refund` is an admin-only alias and additionally requires `transaction_id`.

Settings example:
```json
{"environment":"sandbox","api_version":"v2","client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET","client_version":1,"webhook_username":"YOUR_WEBHOOK_USER","webhook_password":"YOUR_WEBHOOK_PASSWORD"}
```
Toggle example:
```json
{"method":"phonepe","enabled":true}
```
Razorpay and Cashfree toggles are persisted, but remain unavailable to customers until their separate gateway adapters are configured. This implementation does not simulate those gateways.

Refund example (amount in paisa):
```json
{"amount":10000,"reason":"Customer requested refund","request_key":"unique_refund_request_123456"}
```
Only verified completed transactions are refundable. A payment row lock serializes partial refunds, reserves pending/uncertain amounts and prevents over-refunding. Repeating a refund key returns the existing refund. A timeout stays `UNKNOWN`; it is reconciled instead of submitting a duplicate. Refund states are verified through [PhonePe's refund status API](https://developer.phonepe.com/payment-gateway/website-integration/standard-checkout/api-integration/api-reference/refund).

Settlement import example:
```json
{"reference":"MERCHANT_REPORT_20261001_001","environment":"production","amount":100000,"currency":"INR","status":"SETTLED","settled_at":"2026-10-01T12:00:00Z"}
```
Settlement views show imported merchant-dashboard report records with `source=merchant_report`; they are not automatically fetched or inferred from payment success. Sandbox does not move or settle real funds. Import a real merchant report only after reconciling its references and amounts.

Existing dollar-denominated fund/revenue reports exclude INR orders and unpaid/sandbox order states. INR payment totals are displayed separately in this payment management module; they are not added to USD revenue or converted into dollars.

## Frontend

`frontend/static/phonepe-checkout.js` fetches allowed methods and conditionally displays PhonePe for `country === "IN"` and `currency === "INR"`. It sends only the server checkout inputs and handles errors without replacing the user's form. The server independently repeats eligibility, currency, ownership and amount checks. `phonepe-status.js` refreshes the status panel without refreshing the page. Django proxy endpoints retain JWTs in server-side sessions, enforce CSRF and forward a signed IP header.

## Run and test

On the AWS host:
```bash
cd /home/krishna/food
.venv/bin/pip install -r requirements.txt
.venv/bin/python deploy/init-payment-env.py
set -a
source .env
set +a
.venv/bin/python -m backend.migrate_payments
.venv/bin/python -m unittest discover -s tests -p test_phonepe.py -v
```
Tests use the existing PostgreSQL connection within rollback-only transactions and mocked PhonePe responses; no real gateway request or charge is made. They cover country hiding/server rejection, unknown geo, forged geo headers, JWT ownership/admin restrictions, encryption/redaction, idempotency, pending/failed/success verification, sandbox dispatch isolation, callback authentication/deduplication, partial refund reservations and OAuth/signing payloads.

For a separate local installation, use its own PostgreSQL database and `.env`, generate its own encryption/proxy keys, install requirements, run Django migrations/session setup and `backend.migrate_payments`. Serve the customer portal through an HTTPS reverse proxy; callbacks require a publicly reachable HTTPS URL. Set `PHONEPE_CUSTOMER_ORIGIN` to that URL and use the matching webhook in PhonePe's sandbox dashboard. Do not point local tests at production data.

A one-minute reconciliation task retries uncertain/pending payments and refunds using their original references. Callback verification runs immediately in the background; the scheduled task recovers work after a server restart. `/api/admin/payment/logs` exports payment records and redacted audit events as JSON without tokens, credentials or checkout URLs.

The AWS task is installed in `/etc/cron.d/dashvanti-phonepe`. To install the supplied task in the same directory layout:
```bash
sudo install -m 644 deploy/dashvanti-phonepe.cron /etc/cron.d/dashvanti-phonepe
```

## Switch to production

1. Complete PhonePe PG onboarding and UAT; obtain production credentials.
2. Configure the production SHA webhook and valid HTTPS customer origin.
3. In Admin → Payments select **Production**, enter production client and webhook credentials, and explicitly confirm live charging.
4. Verify INR restaurant prices and fee rules, country visibility, success/failure paths, refund verification and merchant settlement reports. Sandbox-created transactions retain their sandbox credentials for later queries.
5. Enable PhonePe after these checks. Use the PhonePe [go-live checklist](https://developer.phonepe.com/payment-gateway/uat-testing-go-live/go-live).

No live PhonePe sandbox authorization, charge, refund or settlement is verified until merchant PG credentials are supplied.
