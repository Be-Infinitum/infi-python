"""Reconciliation: walks whole lists with paginate (customers and payments)."""

from __future__ import annotations

import math
import uuid

from _setup import setup, show, step, uniq

from beinfi import paginate
from beinfi.models import CustomersCreateBody1, ProductOfferValues

infi = setup()

step("Create a product and ~25 customers")
draft_key = str(uuid.uuid4())
draft = infi.products.save_draft(
    path={"draftKey": draft_key},
    body=ProductOfferValues(
        name="Reconciliation product", pricing_model="subscription", currency="BRL", base_price="10.00", billing_cycle="monthly"
    ),
)
product = infi.products.publish_draft(path={"draftKey": draft_key}, if_match=draft.draft_hash)
s = uniq()
total = 25
for i in range(1, total + 1):
    infi.customers.create(body=CustomersCreateBody1(product_id=product.product.id, external_id=f"cus_{s}_{i:02d}"))
show("created", total)

step("Paginate customers.list with limit 10")
# The sandbox account may already have customers from other runs: the proof is that
# pagination repeats no one and that all 25 customers created now show up.
mine = f"cus_{s}_"
seen = 0
ids = set()
ours = set()
for c in paginate(infi.customers.list, query={"limit": 10}):
    seen += 1
    ids.add(c.id)
    if c.external_id and c.external_id.startswith(mine):
        ours.add(c.id)
first = infi.customers.list(query={"limit": 10})
show("items seen", seen)
show("distinct ids", len(ids))
show("created now", len(ours))
show(
    "first page",
    f"{len(first.data)} items, nextCursor={'yes' if first.next_cursor else 'no'}, summary={first.summary.model_dump_json(by_alias=True)}",
)
if len(ids) != seen:
    raise RuntimeError(f"pagination repeated customers: {seen} items, {len(ids)} distinct")
if len(ours) != total:
    raise RuntimeError(f"expected the {total} customers created now, saw {len(ours)}")
print(f"   ✓ {seen} customers in {math.ceil(seen / 10)} pages, no repetition, including the {total} created now")

step("Paginate payments.list")
payments = 0
for _p in paginate(infi.payments.list, query={"limit": 10}):
    payments += 1
show("payments", payments)
if payments == 0:
    print("   (empty: in the local sandbox no payer has paid a link; pagination runs the same, there are just no items)")
