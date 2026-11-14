"""One-time product: product draft -> preview -> link draft -> publish with If-Match."""

from __future__ import annotations

import uuid

from _setup import expect_error, setup, show, step

from beinfi.models import ProductOfferValues, SaveLinkDraftRequest, SaveLinkDraftRequestProduct

infi = setup()

step("Save the one-time product draft")
product_key = str(uuid.uuid4())
saved = infi.products.save_draft(
    path={"draftKey": product_key},
    body=ProductOfferValues(
        name="1-hour mentoring",
        description="One individual session",
        pricing_model="one_time",
        currency="BRL",
        base_price="150.00",
    ),
)
show("draftHash", saved.draft_hash)

step("Read the product preview with ?hash=")
preview = infi.products.get_draft(path={"draftKey": product_key}, query={"hash": saved.draft_hash})
show("offer", f"{preview.offer.name} — {preview.offer.base_price} {preview.offer.currency}")
show("published", preview.published)

step("Save the link draft pointing to the product draft")
link_key = str(uuid.uuid4())
link = infi.links.save_draft(
    path={"draftKey": link_key},
    body=SaveLinkDraftRequest(
        product=SaveLinkDraftRequestProduct(draft_key=product_key),
        success_url="https://example.com/thank-you",
    ),
)
show("link preview", link.preview)
show("link draftHash", link.draft_hash)

step("Publishing the link without If-Match should give 428")
e428 = expect_error(428, lambda: infi.links.publish_draft(path={"draftKey": link_key}))
show("InfiError", f"status={e428.status} code={e428.code}")

step("Publish the link with If-Match = draftHash")
published = infi.links.publish_draft(path={"draftKey": link_key}, if_match=link.draft_hash)
show("published", published.published)
url = published.link.url if published.link else None
show("link URL", url or "(no url)")
if not published.published or not url:
    raise RuntimeError("link was not published with a url")
