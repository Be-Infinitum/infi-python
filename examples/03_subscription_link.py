"""Monthly subscription: same flow of draft -> preview -> publish."""

from __future__ import annotations

import uuid

from _setup import expect_error, setup, show, step

from beinfi.models import ProductOfferValues, SaveLinkDraftRequest, SaveLinkDraftRequestProduct

infi = setup()

step("Save the monthly subscription draft")
product_key = str(uuid.uuid4())
saved = infi.products.save_draft(
    path={"draftKey": product_key},
    body=ProductOfferValues(
        name="Monthly club",
        description="New content every month",
        pricing_model="subscription",
        currency="BRL",
        base_price="29.90",
        billing_cycle="monthly",
    ),
)
show("draftHash", saved.draft_hash)

step("Read the product preview with ?hash=")
preview = infi.products.get_draft(path={"draftKey": product_key}, query={"hash": saved.draft_hash})
show(
    "offer",
    f"{preview.offer.name} — {preview.offer.base_price} {preview.offer.currency}/{preview.offer.billing_cycle}",
)

step("Save the link draft")
link_key = str(uuid.uuid4())
link = infi.links.save_draft(
    path={"draftKey": link_key},
    body=SaveLinkDraftRequest(
        product=SaveLinkDraftRequestProduct(draft_key=product_key),
        success_url="https://example.com/welcome",
        cancel_url="https://example.com/back",
    ),
)
show("link preview", link.preview)

step("Editing the product after the preview invalidates the link hash (412)")
edited = infi.products.save_draft(
    path={"draftKey": product_key},
    body=ProductOfferValues(
        name="Monthly club",
        description="New content every month + community",
        pricing_model="subscription",
        currency="BRL",
        base_price="29.90",
        billing_cycle="monthly",
    ),
    if_match=saved.draft_hash,
)
show("new product draftHash", edited.draft_hash)
stale = expect_error(412, lambda: infi.links.publish_draft(path={"draftKey": link_key}, if_match=link.draft_hash))
show("InfiError", f"status={stale.status} code={stale.code}")

step("Re-read the link preview (new hash) and publish")
fresh = infi.links.get_draft(path={"draftKey": link_key})
published = infi.links.publish_draft(path={"draftKey": link_key}, if_match=fresh.draft_hash)
url = published.link.url if published.link else None
show("link URL", url or "(no url)")
if not published.published or not url:
    raise RuntimeError("link was not published with a url")
