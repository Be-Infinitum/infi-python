"""Prepaid: product with a grant and a per_unit price, wallet credit, consumption and debit by the worker."""

from __future__ import annotations

import time

from _setup import setup, show, sleep, step, uniq

from beinfi.models import (
    CompanyDocument,
    CompanyGrant,
    CompanyMeter,
    CompanyPrice,
    CompanyProduct,
    ConfigApplyBody,
    ConfigPlanBody,
    CustomersCreateBody2,
    FacadeUsageEvent2,
    WalletBalance,
    WalletMutationRequest,
)

infi = setup()
s = uniq()

step("Declare the prepaid product (billing as code)")
document = CompanyDocument(
    schema_version=1,
    products=[
        CompanyProduct(
            key=f"credits-{s}",
            name="AI credits",
            type="agent",
            pricing_model="prepaid",
            currency="BRL",
            base_price="0",
            billing_cycle="monthly",
            meters=[CompanyMeter(key="tokens", unit="token", aggregation="sum")],
            prices=[CompanyPrice(meter="tokens", model="per_unit", unit_amount="0.01")],
            grants=[CompanyGrant(meter="tokens", amount="1000", on="payment")],
        )
    ],
)
plan = infi.config.plan(body=ConfigPlanBody(document=document))
applied = infi.config.apply(body=ConfigApplyBody(document=document), if_match=plan.plan_hash)
show("revision", f"#{applied.revision.number} {applied.revision.status}")

product_key = document.products[0].key
meter = "tokens"
show("productKey / meter", f"{product_key} / {meter}")

step("Create the customer")
external_id = f"user_{uniq()}"
customer = infi.customers.create(body=CustomersCreateBody2(product_key=product_key, external_id=external_id))
wallet_id = customer.enrollment_id
show("enrollmentId (wallet id)", wallet_id)


def balance_of() -> str:
    w = infi.customers.get_wallet(path={"enrollmentId": wallet_id}, query={"meter": meter})
    if isinstance(w, WalletBalance):
        return w.balance
    return next((b.balance for b in w.balances if b.meter == meter), "0")


step("Credit 1000 to the wallet")
credited = infi.customers.credit_wallet(
    path={"enrollmentId": wallet_id},
    body=WalletMutationRequest(meter=meter, amount="1000", reason="initial package"),
)
show("wallet", credited)
before = balance_of()
show("balance before", before)

step("Record consumption of 200")
rec = infi.usage.record(
    body=FacadeUsageEvent2(product_key=product_key, customer_id=external_id, meter=meter, value="200", event_id=f"consumption-{uniq()}")
)
show("event", rec)

step("Wait for the worker to debit (reading the balance every 10s, up to 3 min)")
deadline = time.time() + 3 * 60
after = balance_of()
while after == before and time.time() < deadline:
    sleep(10)
    after = balance_of()
    print(f"   ... balance now: {after}")
show("balance before", before)
show("balance after", after)
if after == before:
    raise RuntimeError("the balance did not go down in 3 minutes: the worker did not debit the prepaid product wallet")
print(f"   ✓ debited: {float(before) - float(after):g}")
