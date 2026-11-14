"""Customer session (portal): create, verify, revoke, verify again (fails)."""

from __future__ import annotations

import uuid

from _setup import expect_error, setup, show, step, uniq

from beinfi.models import CustomerSessionsCreateBody, CustomerSessionsRevokeBody, CustomersCreateBody1, ProductOfferValues

infi = setup()

step("Create a product and a customer")
draft_key = str(uuid.uuid4())
draft = infi.products.save_draft(
    path={"draftKey": draft_key},
    body=ProductOfferValues(
        name="Portal plan", pricing_model="subscription", currency="BRL", base_price="19.90", billing_cycle="monthly"
    ),
)
product = infi.products.publish_draft(path={"draftKey": draft_key}, if_match=draft.draft_hash)
external_id = f"user_{uniq()}"
customer = infi.customers.create(
    body=CustomersCreateBody1(product_id=product.product.id, external_id=external_id, name="Bia", email="bia@example.com")
)
show("customer", customer)

step("Create the session for the externalId")
session = infi.customer_sessions.create(body=CustomerSessionsCreateBody(external_id=external_id))
show("token", f"{session.token[:12]}…")
show("scope / origin / expires", f"{session.scope} / {session.origin} / {session.expires_at.isoformat()}")

step("Verify the token")
verified = infi.customer_sessions.verify(headers={"X-Buyer-Token": session.token})
show("buyer", verified.buyer)
show("access", len(verified.access))
if external_id not in verified.buyer.external_ids:
    raise RuntimeError("the token does not point to the externalId that was created")

step("Revoke the token")
revoked = infi.customer_sessions.revoke(body=CustomerSessionsRevokeBody(token=session.token))
show("revoked", revoked.revoked)

step("Verify again (should fail)")
err = expect_error(401, lambda: infi.customer_sessions.verify(headers={"X-Buyer-Token": session.token}))
show("InfiError", f"status={err.status} code={err.code}")
