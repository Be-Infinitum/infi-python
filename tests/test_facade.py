import pytest

from beinfi import Infi
from beinfi._generated.resources import OPERATIONS

infi = Infi("sk_test_x")


def test_every_contract_operation_has_a_method_on_infi_tag_action():
    assert len(OPERATIONS) == 28
    for o in OPERATIONS:
        res = getattr(infi, o["property"], None)
        assert res is not None, o["operation_id"]
        assert callable(getattr(res, o["method"], None)), o["operation_id"]


def test_expected_names():
    assert callable(infi.customers.get_wallet)
    assert callable(infi.config.plan)
    assert callable(infi.customer_sessions.create)
    assert callable(infi.checkouts.create)
    assert callable(infi.products.set_deliverable)
    assert callable(infi.webhooks.subscribe)


def test_docstring_has_method_path_and_scope():
    doc = infi.webhooks.subscribe.__doc__ or ""
    assert doc.startswith("POST /v1/webhooks (scope config:write)")


def test_parameters_are_keyword_only():
    with pytest.raises(TypeError):
        infi.payments.get("p")  # type: ignore[misc]


def test_context_manager_closes_the_client():
    with Infi("sk_test_x") as c:
        assert c.payments is not None
