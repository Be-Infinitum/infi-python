"""Usage-based billing: usage product (draft), customer, events with an idempotent eventId, consumption per meter."""

from __future__ import annotations

import uuid

from _setup import setup, show, step

from beinfi.models import (
    CustomersCreateBody2,
    FacadeUsageEvent2,
    ProductOfferUsage,
    ProductOfferValues,
)

infi = setup()

step("Create and publish the usage product (draft -> publish)")
draft_key = str(uuid.uuid4())
draft = infi.products.save_draft(
    path={"draftKey": draft_key},
    body=ProductOfferValues(
        name="Summaries API",
        pricing_model="usage",
        currency="BRL",
        usage=ProductOfferUsage(unit="request", unit_amount="0.05", aggregation="count"),
    ),
)
product = infi.products.publish_draft(path={"draftKey": draft_key}, if_match=draft.draft_hash)
product_key = product.product.key
if not product_key:
    raise RuntimeError("product without key")
show("productKey", product_key)

step("Find the meter key (config.pull)")
doc = infi.config.pull()
declared = next((p for p in doc.products if p.key == product.product.key), None)
meter = declared.meters[0].key if declared and declared.meters else None
if not meter:
    raise RuntimeError("the pull did not return the meter of the usage product")
show("meter", meter)

step("Create the customer with externalId")
external_id = f"user_{str(uuid.uuid4())[:8]}"
customer = infi.customers.create(
    body=CustomersCreateBody2(product_key=product_key, external_id=external_id, name="Ana", email="ana@example.com")
)
show("customer", customer)

step("Record usage events (and repeat an eventId)")
for event_id in ["evt-1", "evt-2", "evt-3"]:
    r = infi.usage.record(
        body=FacadeUsageEvent2(product_key=product_key, customer_id=external_id, meter=meter, value="1", event_id=event_id)
    )
    show(event_id, r)
replay = infi.usage.record(
    body=FacadeUsageEvent2(product_key=product_key, customer_id=external_id, meter=meter, value="1", event_id="evt-1")
)
show("evt-1 again", replay)

step("Read the consumption per meter (expected: 3 events, not 4)")
usage = infi.usage.get(query={"enrollmentId": customer.enrollment_id})
for m in usage.meters:
    print(
        f"   - {m.meter}: total={m.total_value} {m.unit}, events={m.event_count}, "
        f"amount={m.total_amount or '-'} {m.currency or ''}"
    )
got = next((m for m in usage.meters if m.meter == meter), None)
if got is None or got.event_count != 3:
    raise RuntimeError(
        f"expected 3 events, got {got.event_count if got else None} "
        "(a repeated eventId should count once)"
    )
print("   ✓ the repeated eventId counted once")
