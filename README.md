# beinfi

The Infi Python SDK, generated from the public API contract (`api/openapi.sdk.json`, a copy of the monorepo's `backend/api/openapi.sdk.json`; ADR 0055).

The contract comes from the monorepo: when `backend/api/openapi.sdk.*` changes, the contract is copied here and the package regenerated. By hand, with the monorepo next to this repo: `INFI_BACKEND=<path>/backend make sync-contract` (copies `api/openapi.sdk.{json,yaml}` and runs `make generate`).

```sh
pip install beinfi   # or: uv add beinfi
```

Python 3.9 or newer. Dependencies: `httpx` and `pydantic>=2`.

```python
import os
from beinfi import Infi, paginate, verify_webhook

infi = Infi(os.environ["INFI_SECRET_KEY"])  # sk_test_ -> sandbox, sk_live_ -> production
```

Methods take keyword arguments only: `path=`, `query=`, `headers=`, `body=` (a `dict` with the wire names or the pydantic model from `beinfi.models`) and the options `idempotency_key=`, `if_match=`, `channel=`. The response comes back as a pydantic model (`checkout.amount_due`, `plan.plan_hash`; names in `snake_case`, with the wire `camelCase` as alias).

- payments: `infi.payments.list(query={"status": "confirmed"})`; `infi.payments.get(path={"paymentId": payment_id})`
- usage: `infi.usage.record(body={"customerId": customer_id, "productId": product_id, "meter": "tokens", "eventId": "e1", "value": "1"})`; `infi.usage.get(query={"enrollmentId": enrollment_id})`
- customers: `infi.customers.get_wallet(path={"enrollmentId": enrollment_id})`; `infi.customers.credit_wallet(...)`
- customer_sessions: `infi.customer_sessions.create(body={"externalId": external_id})`
- products: `saved = infi.products.save_draft(path={"draftKey": draft_key}, body=offer)` and `infi.products.publish_draft(...)`
- links: `infi.links.publish_draft(path={"draftKey": draft_key}, if_match=draft_hash)`
- checkouts: `c = infi.checkouts.create(body={"productId": product_id, "customer": {"externalId": external_id}})`. Send the buyer to `c.url`; `infi.checkouts.get(path={"checkoutId": c.id})` reads `status` and the payments
- webhooks: `infi.webhooks.subscribe(body={"url": url, "events": ["payment.confirmed"]})` (in live it returns `approval_url`); `infi.webhooks.list()`
- delivery: `infi.products.set_deliverable(path={"productId": product_id}, body={"kind": "link", "url": url})`
- config: `plan = infi.config.plan(body={"document": document})` and `infi.config.apply(body={"document": document}, if_match=plan.plan_hash)`

With models, `mypy` flags a wrong field in the body and in the response (see `examples/`):

```python
from beinfi.models import ProductOfferValues

infi.products.save_draft(
    path={"draftKey": draft_key},
    body=ProductOfferValues(name="Mentoring", pricing_model="one_time", currency="BRL", base_price="150.00"),
)
```

Lists paginate by cursor: `for p in paginate(infi.payments.list, query={"limit": 50}): ...`.

Webhooks: `verify_webhook(id=..., timestamp=..., signature=..., body=raw_body, secret=secret)` with the `X-Webhook-Id`, `X-Webhook-Timestamp` and `X-Webhook-Signature` headers and the raw body. `secret` may be a list (rotation); `now` returns Unix seconds.

## Idempotency and If-Match

- Every mutation (POST/PUT/PATCH/DELETE) carries an `Idempotency-Key`. If you do not pass `idempotency_key=`, the SDK generates a uuid4 and reuses the same key on retries (network error, 429, 5xx; up to 3 attempts, waiting 0.25s, 1s and 4s, or the `Retry-After`). 4xx is never retried.
- Publishing and applying require `if_match=` (the hash of the preview or of the plan). If the state changed, the server answers 412 and `InfiError.current` carries the current state so you can show the preview again.
- `channel="panel" | "mcp" | "cli" | "api"` sends `X-Infi-Channel`.
- Errors become `InfiError` (`status`, `code`, `message`, `tracer_id`, `details`, `body`; a network failure has `status == 0` and `code == "network_error"`).
- The response is validated against the contract model: if the server returns something the contract does not describe, `pydantic.ValidationError` shows up right away.
- The client is synchronous (`httpx.Client`, 60s timeout by default) and works as a context manager: `with Infi(key) as infi: ...`.

## This package is generated

Edit the contract (in the monorepo), not the code. `make generate` regenerates `src/beinfi/_generated/`:

- `models.py`: pydantic v2 models from `datamodel-code-generator` (pinned version), built from the contract plus the inline schemas of each operation;
- `resources.py`: `scripts/gen_facade.py` (standard library only) turns each operation into `infi.<tag>.<action>`, with the same validations as the TypeScript SDK's `gen-facade.ts` (an `operationId` that is not `<tag>_<action>` breaks the generator).

Only `_http.py`, `paginate.py`, `webhooks.py` and `__init__.py` are handwritten.

CI (`.github/workflows/ci.yml`) fails if:

- `make check-generated` changes anything in `src/beinfi/_generated/` (the generated code does not match `api/openapi.sdk.json`);
- types (`make typecheck`, which includes `examples/` and `tests/typing_proof.py`), tests (`make test`) or the build (`uv build`) break;
- any example in `examples/` fails against `api-sandbox.beinfi.com`, using the key from the `INFI_SANDBOX_SECRET_KEY` secret. The tests in `tests/` only cover the transport; the proof that the SDK talks to the API is the examples.

Publishing is manual: the `publish` workflow. It redoes the checks, runs the examples and publishes through PyPI trusted publishing (`pypa/gh-action-pypi-publish`, environment `pypi`), with no token.

## Development

```sh
uv sync            # environment and lock (uv.lock is versioned)
make generate      # regenerates src/beinfi/_generated/
make check          # check-generated + typecheck + test + build
```
