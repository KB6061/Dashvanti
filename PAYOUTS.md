# Dashvanti admin revenue and payouts

Revenue is USD from completed orders, grouped by order date in America/Chicago
(override BUSINESS_TIMEZONE in the server environment). Pending payments,
sandbox payments, active orders and other currencies do not inflate revenue.
Commission applies to food after discounts; tax, service fees, delivery fees
and tips are separate. Commission rules are frozen when an order is created.
Refund requests reserve money and reduce payable balances. Rounding preserves
the order total: restaurant + driver + platform + tax + refunds = total.

## Admin controls

Open Fund Management → Quick Pay to enable manual receipts or Stripe Connect.
Stripe keys are encrypted in PostgreSQL and are never returned to the browser.
Test and live credentials and recipients are separate. Live mode requires
explicit confirmation. Connect recipients must finish Stripe onboarding,
activate transfers and enable payouts. Use the recipient's acct_... ID.

Double-click Payout driver/Payout restaurant in their respective payout page.
Manual mode requires the confirmation number of a transfer already completed
outside Dashvanti. The receipt, confirmation, recipient, amount, status and
timestamps are stored in the database.

Stripe mode transfers USD from the platform's available Stripe balance to the
connected account. Its bank payout schedule is managed by Stripe. TRANSFERRED
confirms a connected-account transfer, not arrival in a bank account.
TEST_TRANSFERRED never settles a real payable balance. Platform Stripe funds
are required; a Card label on an order does not fund the Stripe balance.

Re-check uncertain transfers from Quick Pay history. Their balance stays
reserved, and retries reuse the same idempotency key. Partially reversed
transfers require review; do not issue another payout while under review.

## APIs (HTTPS, admin authentication)

- GET/PUT /api/operations/funds/payout-settings
- PUT /api/operations/funds/payout-recipient
- POST /api/operations/funds/quick-pay
- POST /api/operations/funds/payouts/{id}/status

Payout payload:

```json
{"order_id":123,"payee_role":"driver","mode":"manual","confirmation":"BANK-REFERENCE","expected_amount":"5.00"}
```

For Stripe, mode is stripe and confirmation is optional. The server calculates
the payable amount and verifies expected_amount before creating a receipt.
Database-backed tests use transaction rollback and mock Stripe; no live money
is transferred by the tests.

Stripe references:
- https://docs.stripe.com/connect/separate-charges-and-transfers
- https://docs.stripe.com/api/transfers/create
- https://docs.stripe.com/connect/payouts-connected-accounts
