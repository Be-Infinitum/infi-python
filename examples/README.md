# SDK examples

One script per billing use case, written only with the SDK's public API (`infi.<tag>.<method>`, `paginate`, `InfiError`, the models in `beinfi.models`). They import the package installed in the environment (`uv sync`).

## How to run

```sh
INFI_SECRET_KEY=sk_test_... uv run python examples/01_billing_as_code.py
INFI_SECRET_KEY=sk_test_... uv run python examples/run_all.py   # all of them, with ✓/✗ at the end (or: make examples)
```

- `INFI_SECRET_KEY` (required): an `sk_test_` key from a sandbox account that has an owner. The anonymous account (`/public/v1/claimables`) was removed in ADR 0076. Examples 01 and 05 apply config documents to the account: use an account just for the examples. They were written for a clean account on each run; running again on the same account has not been verified yet.
- `INFI_API_URL` (optional): without it, the SDK uses `https://api-sandbox.beinfi.com` for `sk_test_`. For the local backend, `INFI_API_URL=http://127.0.0.1:8088`.
- Types: `make typecheck` (mypy) covers `examples/` together with the package: a wrong field name in an example breaks CI.

## What each script shows

| Script | Demonstrates |
|---|---|
| `01_billing_as_code.py` | Document with a subscription, a usage-based product and a prepaid one with a grant; plan, apply with `if_match=plan.plan_hash`, pull; apply with a stale hash gives 412, without If-Match gives 428 |
| `02_one_time_link.py` | One-time product: draft, preview with `draft_hash`, link draft, publish (428 without If-Match) and the link URL |
| `03_subscription_link.py` | Same flow for a monthly subscription, plus the 412 when the product changes after the preview |
| `04_usage_based.py` | Usage-based product, customer by productKey, events with a repeated `event_id` counting once, consumption per meter |
| `05_prepaid_credits.py` | Prepaid declared in config, a credit of 1000 to the wallet, consumption of 200 and waiting for the worker's debit (up to 3 min) |
| `06_customer_session.py` | Portal session: create, verify, revoke and verify again (401) |
| `07_reconciliation.py` | `paginate` over `customers.list` (25 customers, limit 10) and `payments.list` |
| `08_checkout_delivery_webhook.py` | Sale to a buyer: published product, delivery by link, subscribed webhook, checkout with the hosted URL and the read that waits for the payment |

## Script to SDK operations

| Script | Operations |
|---|---|
| 01 | `config.plan`, `config.apply`, `config.pull` |
| 02 | `products.save_draft`, `products.get_draft`, `links.save_draft`, `links.publish_draft` |
| 03 | `products.save_draft`, `products.get_draft`, `links.save_draft`, `links.get_draft`, `links.publish_draft` |
| 04 | `products.save_draft`, `products.publish_draft`, `config.pull`, `customers.create`, `usage.record`, `usage.get` |
| 05 | `config.plan`, `config.apply`, `config.pull`, `products.save_draft`, `products.publish_draft`, `customers.create`, `customers.credit_wallet`, `customers.get_wallet`, `usage.record` |
| 06 | `products.save_draft`, `products.publish_draft`, `customers.create`, `customer_sessions.create`, `customer_sessions.verify`, `customer_sessions.revoke` |
| 07 | `products.save_draft`, `products.publish_draft`, `customers.create`, `customers.list` and `payments.list` via `paginate` |
| 08 | `products.save_draft`, `products.publish_draft`, `products.set_deliverable`, `products.get_deliverable`, `webhooks.subscribe`, `webhooks.list`, `checkouts.create`, `checkouts.get` |
