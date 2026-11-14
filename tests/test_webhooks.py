import hashlib
import hmac
import time

from beinfi import verify_webhook

SECRET = "whsec_test"
BODY = '{"type":"payment.succeeded"}'
NOW = int(time.time())


def sign(id_, ts, body, secret=SECRET):
    return "v1=" + hmac.new(secret.encode(), f"{id_}.{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def req(**over):
    base = {"id": "evt_1", "timestamp": str(NOW), "signature": sign("evt_1", NOW, BODY), "body": BODY, "secret": SECRET}
    base.update(over)
    return base


def test_valid_signature_passes():
    assert verify_webhook(**req()) is True


def test_accepts_bytes_and_several_signatures_rotation():
    sig = f"{sign('evt_1', NOW, BODY, 'old')} {sign('evt_1', NOW, BODY)}"
    assert verify_webhook(**req(signature=sig, body=BODY.encode())) is True


def test_accepts_list_of_secrets():
    assert verify_webhook(**req(secret=["old", SECRET])) is True


def test_tampered_body_fails():
    assert verify_webhook(**req(body=BODY + " ")) is False


def test_wrong_id_secret_or_format_fail():
    assert verify_webhook(**req(id="evt_2")) is False
    assert verify_webhook(**req(secret="outro")) is False
    assert verify_webhook(**req(signature="abc")) is False


def test_old_or_future_timestamp_fails():
    old = NOW - 400
    kw = {"timestamp": str(old), "signature": sign("evt_1", old, BODY)}
    assert verify_webhook(**req(**kw)) is False
    assert verify_webhook(**req(**kw), tolerance_seconds=500) is True
    fut = NOW + 400
    assert verify_webhook(**req(timestamp=str(fut), signature=sign("evt_1", fut, BODY))) is False


def test_non_integer_timestamp_fails():
    assert verify_webhook(**req(timestamp="abc")) is False
    assert verify_webhook(**req(timestamp=f"{NOW}.5")) is False


def test_now_is_injectable_in_seconds():
    assert verify_webhook(**req(), now=lambda: NOW + 10) is True
    assert verify_webhook(**req(), now=lambda: NOW + 1000) is False


def test_hex_with_trailing_garbage_like_node():
    good = sign("evt_1", NOW, BODY)
    assert verify_webhook(**req(signature=good + "zz")) is True
    assert verify_webhook(**req(signature="v1=")) is False
