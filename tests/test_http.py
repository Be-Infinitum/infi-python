import json

import httpx
import pytest

from beinfi import Infi, InfiError
from beinfi._http import Request, Transport, parse_error, retry_after_seconds

REC = {"customerId": "c", "meter": "m", "value": "1", "eventId": "e", "productId": "p"}
OK_REC = {"accepted": 1}
PID = "prod_" + "a" * 22
INV = "inv_" + "b" * 22


def setup(responses, secret="sk_live_x", **kw):
    calls = []
    sleeps = []
    state = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        r = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        if isinstance(r, Exception):
            raise r
        return r

    infi = Infi(secret, transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return infi, calls, sleeps


def js(status, body, headers=None):
    return httpx.Response(status, json=body, headers=headers)


def test_url_from_key_and_bearer_post_sends_uuid_idempotency_key():
    infi, calls, _ = setup([js(202, OK_REC)])
    infi.usage.record(body=REC)
    c = calls[0]
    assert str(c.url).startswith("https://api.beinfi.com/v1/usage/events")
    assert c.headers["authorization"] == "Bearer sk_live_x"
    assert c.headers["accept"] == "application/json"
    assert len(c.headers["idempotency-key"]) == 36
    assert c.headers["content-type"] == "application/json"


def test_get_does_not_send_idempotency_key():
    infi, calls, _ = setup([js(200, {"data": [], "nextCursor": None})])
    infi.payments.list()
    assert "idempotency-key" not in calls[0].headers


def test_explicit_api_url_beats_sandbox_by_prefix_and_invalid_key():
    infi, calls, _ = setup([js(200, {"data": [], "nextCursor": None})], secret="sk_test_x", api_url="http://localhost:8088/")
    infi.payments.list()
    assert str(calls[0].url).startswith("http://localhost:8088/v1/payments")
    infi2, calls2, _ = setup([js(200, {"data": [], "nextCursor": None})], secret="sk_test_x")
    infi2.payments.list()
    assert str(calls2[0].url).startswith("https://api-sandbox.beinfi.com/v1/payments")
    with pytest.raises(ValueError):
        Infi("bad")
    with pytest.raises(ValueError):
        Infi("")


def test_503_retries_with_the_same_idempotency_key_then_succeeds():
    infi, calls, sleeps = setup([js(503, {}), js(503, {}), js(202, {"ok": 1})])
    res = infi.usage.record(body=REC)
    assert res.model_dump() == {"ok": 1}
    assert len(calls) == 3
    assert len({c.headers["idempotency-key"] for c in calls}) == 1
    assert sleeps == [0.25, 1.0]


def test_network_error_retries_and_gives_up_after_3_attempts():
    infi, calls, sleeps = setup([httpx.ConnectError("boom")])
    with pytest.raises(InfiError) as e:
        infi.usage.record(body=REC)
    assert e.value.code == "network_error" and e.value.status == 0
    assert len(calls) == 3
    assert sleeps == [0.25, 1.0]


def test_400_is_not_retried():
    infi, calls, _ = setup([js(400, {"error_code": "bad_request", "message": "x", "tracer_id": "t1"})])
    with pytest.raises(InfiError) as e:
        infi.usage.record(body=REC)
    assert (e.value.status, e.value.code, e.value.tracer_id) == (400, "bad_request", "t1")
    assert len(calls) == 1


def test_nested_envelope_becomes_infi_error():
    infi, _, _ = setup([js(409, {"error": {"code": "idempotency_key_reused", "message": "m", "request_id": "r9"}})])
    with pytest.raises(InfiError) as e:
        infi.usage.record(body=REC)
    err = e.value
    assert (err.status, err.code, err.message, err.tracer_id) == (409, "idempotency_key_reused", "m", "r9")
    assert str(err) == "m"


def test_flat_envelope_with_errors_keeps_details():
    infi, _, _ = setup([js(422, {"error_code": "validation_failed", "message": "m", "tracer_id": "t", "errors": [{"field": "a"}]})])
    with pytest.raises(InfiError) as e:
        infi.usage.record(body=REC)
    assert e.value.details == [{"field": "a"}]
    assert e.value.body["error_code"] == "validation_failed"


def test_412_carries_current():
    infi, _, _ = setup([js(412, {"error_code": "plan_changed", "message": "m", "tracer_id": "t", "current": {"planHash": "H2"}})])
    with pytest.raises(InfiError) as e:
        infi.config.apply(body={"document": {}}, if_match='"H1"')
    assert e.value.status == 412
    assert e.value.current == {"planHash": "H2"}


def test_retry_after_is_honored_on_429():
    infi, _, sleeps = setup(
        [js(429, {"error": {"code": "rate_limited", "message": "m", "request_id": "r"}}, {"Retry-After": "2"}), js(202, {})]
    )
    infi.usage.record(body=REC)
    assert sleeps == [2.0]


def test_retry_after_as_http_date_and_invalid():
    assert retry_after_seconds(None) is None
    assert retry_after_seconds("abc") is None
    assert retry_after_seconds("nan") is None
    assert retry_after_seconds("-5") == 0.0
    assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


def test_204_returns_none():
    t = Transport("sk_test_x", transport=httpx.MockTransport(lambda r: httpx.Response(204)))
    assert t.request(Request(method="POST", path="/v1/x")) is None


def test_plain_text_becomes_message_and_empty_body_becomes_http_status():
    e = parse_error(502, "bad gateway")
    assert (e.code, e.message, e.body) == ("http_502", "bad gateway", "bad gateway")
    e = parse_error(500, "")
    assert (e.code, e.message, e.body) == ("http_500", "HTTP 500", None)
    assert parse_error(412, '{"current":1}').current == 1
    assert parse_error(400, '{"current":1}').current is None


def test_builds_url_path_params_query_body_and_options():
    infi, calls, _ = setup(
        [
            js(200, {"balance": "1", "meter": "m1", "total": "1"}),
            js(200, {"revision": {"id": "r"}}),
        ],
        secret="sk_test_x",
    )
    infi.customers.get_wallet(path={"enrollmentId": "c 1/é"}, query={"meter": "m1", "x": None, "flag": True})
    with pytest.raises(Exception):  # the mock response is not a valid result; only the request matters
        infi.config.apply(body={"document": {}}, if_match='"h"', channel="cli", idempotency_key="k1")
    assert str(calls[0].url) == "https://api-sandbox.beinfi.com/v1/customers/c%201%2F%C3%A9/wallet?meter=m1&flag=true"
    h = calls[1].headers
    assert h["if-match"] == '"h"'
    assert h["x-infi-channel"] == "cli"
    assert h["idempotency-key"] == "k1"
    assert calls[1].content == b'{"document":{}}'


def test_missing_path_param_is_a_clear_error():
    infi, calls, _ = setup([js(200, {})])
    with pytest.raises(ValueError, match="enrollmentId"):
        infi.customers.get_wallet(path={})
    assert calls == []


def test_models_become_json_with_wire_names_and_response_becomes_model():
    from beinfi.models import CheckoutCreateRequest

    checkout = {
        "id": INV, "status": "open", "url": "https://pay.example/invoices/x", "total": "19.00",
        "currency": "BRL", "amountDue": "19.00", "createdAt": "2026-11-13T10:00:00Z", "payments": [],
    }
    infi, calls, _ = setup([js(201, checkout)], secret="sk_test_x")
    body = CheckoutCreateRequest.model_validate({"productId": PID, "customer": {"externalId": "b1"}})
    out = infi.checkouts.create(body=body)
    assert json.loads(calls[0].content) == {"productId": PID, "customer": {"externalId": "b1"}}
    assert out.id == INV and out.amount_due == "19.00"


def test_caller_headers_pass_through_and_get_gets_no_idempotency_key():
    infi, calls, _ = setup([js(200, {"buyer": {}, "access": []})])
    try:
        infi.customer_sessions.verify(headers={"X-Buyer-Token": "bt_1"})
    except Exception:
        pass  # the mock response is not valid; only the request matters
    assert calls[0].headers["x-buyer-token"] == "bt_1"
    assert "idempotency-key" not in calls[0].headers
