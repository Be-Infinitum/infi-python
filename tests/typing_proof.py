"""Type proof (runs in `mypy`, not pytest): the generated types must not turn into Any.

Each `# type: ignore[...]` marks an error that mypy MUST report. With `strict`
(`warn_unused_ignores`), if the type stops catching the error, the ignore is left over and mypy
fails. It is the equivalent of `_types()` with `@ts-expect-error` in the TypeScript SDK.
"""

from __future__ import annotations

from beinfi import Infi
from beinfi.models import CustomersGetPath, ProductOfferValues

infi = Infi("sk_test_x")


def _types() -> None:
    # path is required when the operation has a path parameter
    infi.customers.get()  # type: ignore[call-arg]
    # the path model requires customer_id
    infi.customers.get(path=CustomersGetPath())  # type: ignore[call-arg]
    # unknown argument
    infi.payments.list(nope=1)  # type: ignore[call-arg]
    # parameters are keyword-only
    infi.payments.get({"paymentId": "p"})  # type: ignore[call-arg]
    # channel only accepts the four channels
    infi.payments.list(channel="fax")  # type: ignore[arg-type]
    # nonexistent field on the response
    r = infi.payments.get(path={"paymentId": "p"})
    r.nao_existe  # type: ignore[attr-defined]
    # product draft: real typed fields
    pd = infi.products.get_draft(path={"draftKey": "k"})
    pd.draft_hash.upper()
    pd.offer.name.upper()
    pd.nao_existe  # type: ignore[attr-defined]
    # link draft
    ld = infi.links.get_draft(path={"draftKey": "k"})
    ld.preview.currency.upper()
    ld.nao_existe  # type: ignore[attr-defined]
    # body: wrong field name, wrong type and value outside the enum
    ProductOfferValues(nome="x")  # type: ignore[call-arg]
    ProductOfferValues(name=1, pricing_model="one_time", currency="BRL")  # type: ignore[arg-type]
    ProductOfferValues(name="x", pricing_model="mensal", currency="BRL")  # type: ignore[arg-type]
