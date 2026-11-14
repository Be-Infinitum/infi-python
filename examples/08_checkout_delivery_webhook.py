"""Sale to a buyer: published product -> delivery by URL -> webhook -> checkout -> wait for the payment."""

from __future__ import annotations

import uuid

from _setup import setup, show, step

from beinfi import InfiError
from beinfi.models import (
    CheckoutCreateRequest,
    CheckoutCreateRequestCustomer,
    ProductOfferValues,
    PutDeliverableRequest,
    WebhookSubscribeRequest,
)

infi = setup()

step("Publish a one-time product")
draft_key = str(uuid.uuid4())
saved = infi.products.save_draft(
    path={"draftKey": draft_key},
    body=ProductOfferValues(name="PDF guide", pricing_model="one_time", currency="BRL", base_price="19.00"),
)
published = infi.products.publish_draft(path={"draftKey": draft_key}, if_match=saved.draft_hash)
product_id = published.product.id
if not product_id:
    raise RuntimeError("the product was not published with an id")
show("productId", product_id)

step("Set the delivery: the buyer receives this URL after paying")
infi.products.set_deliverable(
    path={"productId": product_id},
    body=PutDeliverableRequest(kind="link", url="https://example.com/guide.pdf"),
)
deliverable = infi.products.get_deliverable(path={"productId": product_id})
show("delivery", deliverable)

step("Subscribe a webhook to learn about the payment")
# In the sandbox it applies right away and returns the secret once; in live it returns approvalUrl for a person to approve.
# If the sandbox does not have the secret vault configured yet, it answers 503: the step is skipped.
try:
    hook = infi.webhooks.subscribe(
        body=WebhookSubscribeRequest(url="https://example.com/hooks/infi", events=["payment.confirmed"])
    )
    show(
        "webhook",
        f"{hook.status}{' (secret received)' if hook.secret else ''}"
        f"{f' approve at {hook.approval_url}' if hook.approval_url else ''}",
    )
    listed = infi.webhooks.list()
    show("webhooks", [w.url for w in listed.data])
except InfiError as e:
    if e.status != 503:
        raise
    show("webhook", "503: the sandbox does not store webhook secrets yet")

step("Open a buyer checkout")
checkout = infi.checkouts.create(
    body=CheckoutCreateRequest(
        product_id=product_id,
        customer=CheckoutCreateRequestCustomer(external_id=f"buyer_{str(uuid.uuid4())[:8]}", email="buyer@example.com"),
    )
)
show("checkout", f"{checkout.id} {checkout.status} {checkout.total} {checkout.currency}")
show("send the buyer to", checkout.url)
if f"/invoices/{checkout.id}" not in checkout.url:
    raise RuntimeError("checkout url does not point to the invoice")

step("Read the checkout: this is how the code waits for the payment")
again = infi.checkouts.get(path={"checkoutId": checkout.id})
show("status", again.status)
show("payments", len(again.payments))
if again.id != checkout.id:
    raise RuntimeError("the checkout read is not the one created")
