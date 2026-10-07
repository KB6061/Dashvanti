# Dashvanti account enhancements

Account, support, review, wallet and audit enhancements for the existing Django/FastAPI checkout. Follow-up work adds all listed wallet adapters and binds existing admin actions to authenticated database identities. Real payment tests require merchant credentials.

## Apply

Review the patch against your current checkout first. Its baseline comes from previously downloaded snapshots; newer server changes may require resolving patch conflicts. Do not replace existing files wholesale.

```sh
git apply --check account-enhancements.patch
git apply account-enhancements.patch
python -m backend.migrate_account_enhancements
```

Use the project's existing environment, dependency installation and process manager. Additional imports: Pillow, python-multipart; optional maxminddb for local city detection. Existing HTTPX, SQLAlchemy, Django, FastAPI, JWT and payment dependencies remain required.

Configure restaurant regions before enabling strict city filtering. Admin Gateway Controls includes restaurant/promotion region settings. Optional backfill uses the existing configured geocoder and makes external geocoding requests:

```sh
python -m backend.account_region_backfill
```

Customer account navigation replaces only the right panel. Support Center, wallet, favorites and review panels use `/api/account-experience` through same-origin authenticated Django proxies. Existing support ticket IDs become globally shared `INC` identifiers. Existing reviews require moderation before becoming public. Existing promotions require explicit region configuration.

## Admin authentication

Sign in at `/admin/login` or `/admin/account-login`. Enter an individual admin email/password, or leave the email blank to use the existing configured system-administrator password. System-administrator sessions are bound to the existing administrator database record. Sign-in attempts are limited using Redis. The internal admin API requires both the existing secret and a valid admin JWT.

New pages: `/admin/support-center`, `/admin/audit-center`, `/admin/gateway-controls`, `/admin/review-moderation`, `/admin/account-verification`, `/admin/wallet-refunds`. Approved public reviews are available at `/reviews` on all portals and the main website.

Audit capture covers authenticated admin ORM changes, bulk updates/deletes and nested sessions in the request context. Both API and portal requests are logged, including failures. Existing shared-password sessions must sign in again to obtain JWTs. PostgreSQL protects the audit table from updates/deletions with an immutable trigger. Direct SQL outside application requests has no admin identity and is outside application audit capture.

Rollback requires an explicit `account_admin_permissions.audit_rollback` grant. Only allowlisted nonfinancial fields can be restored; conflicting changes, deleted records, payments and credentials cannot be rolled back.

## Payment setup

Wallet checkout/status adapters: Stripe cards, Apple Pay and Google Pay; Stripe Cash App Pay; PayPal; Square; Authorize.Net Accept Hosted; Razorpay and UPI; PhonePe v2; Paytm. India Google Pay uses the UPI flow. Configure credentials before enabling each gateway. PhonePe uses the existing encrypted admin settings. Sandbox successes are recorded as tests and never increase spendable wallet funds.

Webhook URLs:

```text
/api/account-experience/wallet/callback/stripe
/api/account-experience/wallet/callback/paypal
/api/account-experience/wallet/callback/razorpay
/api/account-experience/wallet/callback/phonepe
/api/account-experience/wallet/callback/square
/api/account-experience/wallet/callback/authorize_net
/api/account-experience/wallet/callback/paytm
```

Use the publicly accessible same-origin callback `/customer/wallet-webhook/{provider}` on the customer domain; it forwards raw signed payloads to the internal API. Set Square's webhook URL environment variable to exactly the URL registered with Square. Authorize.Net sends transaction notifications; their signatures and server transaction details bind the payment to the customer/invoice. Paytm callbacks use signed form data. All callbacks recheck provider status and amount before crediting funds. The existing authenticated PhonePe callback also recognizes wallet funding references.

Apple Pay, Google Pay and Cash App require compatible devices and enabled merchant capabilities. Admin flags control the portal options and wallet buttons. Stripe wallet checkout uses Payment/Express Checkout Elements, rather than unmanaged hosted wallet buttons. Square checkout receives explicit wallet enable/disable flags. Razorpay offers net banking on its merchant-hosted checkout when enabled in the merchant account.

`/admin/wallet-refunds` credits a pending refund request only against a verified production order payment. Gateway and wallet refunds share a locked remaining-payment limit. Repeated credits are idempotent. Cash orders and unverified payments cannot mint wallet credits. Never credit a wallet and issue a gateway refund for the same amount.

UPI, PhonePe, Razorpay and Paytm are restricted to India. PayPal, Square, Authorize.Net and Cash App funding use USD. India Google Pay uses UPI; Apple Pay is hidden in India. Unknown countries do not become India by inference. Browser geolocation requires permission; optional city GeoIP uses a local database. Current delivery addresses remain the source of regional checkout eligibility.

Provider references: [Square Checkout](https://developer.squareup.com/docs/checkout-api), [Authorize.Net Accept Hosted](https://developer.authorize.net/api/reference/features/accept-hosted.html), [Paytm Initiate Transaction](https://www.paytmpayments.com/docs/api/initiate-transaction-api/), [official Paytm checksum SDK](https://github.com/paytm/Paytm_Python_Checksum).

## Local verification

```bat
set PYTHONUTF8=1
py -3.11 verify_account_enhancements_local.py
py -3.11 render_account_enhancements_preview.py
node account-enhancements\verification\test_account_panels.cjs
```

Backend tests use local SQLite and mocked provider calls. Browser tests intercept all requests locally. PostgreSQL/Oracle concurrency, real payment callbacks, deployed portal behavior and real-device geolocation still require validation in the target environment.
