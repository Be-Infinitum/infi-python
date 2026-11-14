import json
from pathlib import Path

import pytest

from gen_facade import ContractError, collect_ops, generate, plan_signatures


def op(**over):
    base = {
        "operationId": "payments_list",
        "tags": ["payments"],
        "x-infi-facade": True,
        "x-infi-scope": "payments:read",
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def doc(o):
    return {"paths": {"/v1/payments": {"get": o}}}


def test_accepts_valid_operation_and_generates_snake_case_name():
    ops = collect_ops(doc(op(operationId="customers_get_wallet", tags=["customers"])))
    assert ops[0].action == "get_wallet"
    assert "def get_wallet(" in generate(ops)


def test_rejects_operation_id_outside_the_pattern():
    with pytest.raises(ContractError, match=r"payments_<snake_case action"):
        collect_ops(doc(op(operationId="listPayments")))


def test_rejects_operation_without_x_infi_scope():
    with pytest.raises(ContractError, match="x-infi-scope"):
        collect_ops(doc(op(**{"x-infi-scope": None})))


def test_rejects_two_tags():
    with pytest.raises(ContractError, match="exactly one tag"):
        collect_ops(doc(op(tags=["payments", "usage"])))


def test_rejects_duplicate_and_missing_facade():
    d = {"paths": {"/a": {"get": op()}, "/b": {"get": op()}}}
    with pytest.raises(ContractError, match="duplicate"):
        collect_ops(d)
    with pytest.raises(ContractError, match="x-infi-facade"):
        collect_ops(doc(op(**{"x-infi-facade": None})))


def test_rejects_empty_contract_missing_operation_id_and_bad_tag():
    with pytest.raises(ContractError, match="contract has no operations"):
        collect_ops({"paths": {}})
    with pytest.raises(ContractError, match="missing operationId"):
        collect_ops(doc(op(operationId=None)))
    with pytest.raises(ContractError, match="is not snake_case"):
        collect_ops(doc(op(tags=["Payments"])))


def test_rejects_action_that_is_a_python_reserved_word():
    with pytest.raises(ContractError, match="reserved word"):
        collect_ops(doc(op(operationId="payments_import")))


def test_signatures_param_body_and_response():
    d = {
        "components": {"schemas": {"Out": {"type": "object"}}},
        "paths": {
            "/v1/things/{id}": {
                "parameters": [{"in": "path", "name": "id", "required": True, "schema": {"type": "string"}}],
                "put": op(
                    operationId="things_save",
                    tags=["things"],
                    parameters=[
                        {"in": "header", "name": "If-Match", "schema": {"type": "string"}},
                        {"in": "header", "name": "Accept-Language", "schema": {"type": "string"}},
                        {"in": "query", "name": "hash", "schema": {"type": "string"}},
                    ],
                    requestBody={"required": True, "content": {"application/json": {"schema": {"type": "object"}}}},
                    responses={"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Out"}}}}},
                ),
            }
        },
    }
    ops = collect_ops(d)
    sigs, extra = plan_signatures(d, ops)
    sig = sigs[0]
    assert sig.path and sig.path.required
    assert sig.query and not sig.query.required
    # If-Match belongs to the transport: only Accept-Language is left in the headers.
    assert sig.headers and list(extra["ThingsSaveHeaders"]["properties"]) == ["Accept-Language"]
    assert sig.body == "m.ThingsSaveBody" and sig.body_required
    assert sig.responses == {200: "m.Out"}
    code = generate(ops, sigs)
    compile(code, "resources.py", "exec")
    assert "path: Union[m.ThingsSavePath, Mapping[str, Any]]," in code


def test_real_contract_has_28_operations_and_generates_valid_code():
    root = Path(__file__).resolve().parent.parent
    contract = json.loads((root / "api" / "openapi.sdk.json").read_text(encoding="utf-8"))
    ops = collect_ops(contract)
    assert len(ops) == 28
    sigs, _ = plan_signatures(contract, ops)
    compile(generate(ops, sigs), "resources.py", "exec")
