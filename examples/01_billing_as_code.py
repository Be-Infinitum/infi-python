"""Billing as code: declare the company in a document, plan, apply and check with pull."""

from __future__ import annotations

from _setup import expect_error, setup, show, step, uniq

from beinfi.models import (
    CompanyDocument,
    CompanyGrant,
    CompanyMeter,
    CompanyPrice,
    CompanyProduct,
    ConfigApplyBody,
    ConfigPlanBody,
)

infi = setup()
s = uniq()

document = CompanyDocument(
    schema_version=1,
    products=[
        CompanyProduct(
            key=f"subscription-{s}",
            name="Pro plan",
            type="item",
            pricing_model="subscription",
            currency="BRL",
            base_price="49.90",
            billing_cycle="monthly",
        ),
        CompanyProduct(
            key=f"usage-{s}",
            name="Usage-based API",
            type="agent",
            pricing_model="usage",
            currency="BRL",
            meters=[CompanyMeter(key="requests", unit="request", aggregation="count")],
            prices=[CompanyPrice(meter="requests", model="per_unit", unit_amount="0.05")],
        ),
        CompanyProduct(
            key=f"prepaid-{s}",
            name="AI credits",
            type="agent",
            pricing_model="prepaid",
            currency="BRL",
            base_price="0",
            billing_cycle="monthly",
            meters=[CompanyMeter(key="tokens", unit="token", aggregation="sum")],
            prices=[CompanyPrice(meter="tokens", model="per_unit", unit_amount="0.01")],
            grants=[CompanyGrant(meter="tokens", amount="1000", on="payment")],
        ),
    ],
)

step("Plan the document (writes nothing)")
plan = infi.config.plan(body=ConfigPlanBody(document=document))
show("planHash", plan.plan_hash)
show("mode", f"{plan.mode}, hasChanges={plan.has_changes}, blocked={plan.blocked}")
for c in plan.changes:
    print(f"   - [{c.action}] {c.resource} {c.ref}: {c.sentence}")

step("Apply with If-Match = planHash")
applied = infi.config.apply(body=ConfigApplyBody(document=document), if_match=plan.plan_hash)
show("revision", f"#{applied.revision.number} status={applied.revision.status} mode={applied.revision.mode}")

step("Apply again with the stale hash should give 412")
stale = expect_error(412, lambda: infi.config.apply(body=ConfigApplyBody(document=document), if_match=plan.plan_hash))
show("InfiError", f'status={stale.status} code={stale.code} message="{stale.message}"')
current = stale.current
show("current.planHash (recomputed plan)", current.get("planHash") if isinstance(current, dict) else "(no current)")

step("Apply without If-Match should give 428")
no_match = expect_error(428, lambda: infi.config.apply(body=ConfigApplyBody(document=document)))
show("InfiError", f"status={no_match.status} code={no_match.code}")

step("Pull the document from the server and check the products")
pulled = infi.config.pull()
for p in pulled.products:
    print(
        f"   - {p.key} ({p.pricing_model}) meters={len(p.meters or [])} "
        f"prices={len(p.prices or [])} grants={len(p.grants or [])}"
    )
for p in document.products:
    got = next((x for x in pulled.products if x.key == p.key), None)
    if got is None:
        raise RuntimeError(f"product {p.key} did not come back in the pull")
    if got.pricing_model != p.pricing_model:
        raise RuntimeError(f"{p.key}: pricingModel {got.pricing_model} != {p.pricing_model}")
print("   ✓ all 3 products came back")

step("Plan again: nothing to change")
again = infi.config.plan(body=ConfigPlanBody(document=document))
show("hasChanges", again.has_changes)
if again.has_changes:
    raise RuntimeError("plan after apply still has changes")
