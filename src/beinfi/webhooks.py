"""Handwritten layer (ADR 0055, D3): webhook verification.

Scheme from backend/internal/messaging/webhook/signer.go:
  signed_content = id + "." + timestamp + "." + body
  signature      = "v1=" + hex(HMAC_SHA256(secret, signed_content))
The header may carry several signatures separated by spaces (rotation).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from typing import Callable, List, Optional, Sequence, Union

_HEX = set("0123456789abcdefABCDEF")


def _lenient_hex(s: str) -> bytes:
    """Like Node's Buffer.from(s, "hex"): stops at the first invalid pair and ignores a trailing nibble."""
    out = bytearray()
    for i in range(0, len(s) - 1, 2):
        pair = s[i : i + 2]
        if pair[0] not in _HEX or pair[1] not in _HEX:
            break
        out.append(int(pair, 16))
    return bytes(out)


def _integer(value: Union[str, int, float]) -> Optional[int]:
    """Number(x) followed by Number.isInteger: returns the integer or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        s = value.strip()
        try:
            n = float(s) if s else 0.0
        except ValueError:
            return None
    else:
        n = float(value)
    return int(n) if math.isfinite(n) and n == int(n) else None


def verify_webhook(
    *,
    id: str,  # noqa: A002 - it is the X-Webhook-Id header
    timestamp: Union[str, int],
    signature: str,
    body: Union[str, bytes, bytearray, memoryview],
    secret: Union[str, Sequence[str]],
    tolerance_seconds: float = 300,
    now: Optional[Callable[[], float]] = None,
) -> bool:
    """Verifies the signature of an Infi webhook.

    `id`, `timestamp` and `signature` are the `X-Webhook-Id`,
    `X-Webhook-Timestamp` and `X-Webhook-Signature` headers; `body` is the raw body,
    exactly as received. `secret` may be a list (secret rotation).
    `now` returns Unix seconds (default: `time.time`).
    """
    ts = _integer(timestamp)
    if ts is None:
        return False
    current = (now or time.time)()
    if abs(current - ts) > tolerance_seconds:
        return False
    candidates: List[str] = []
    for part in signature.split():
        i = part.find("=")
        if i < 0 or part[:i] != "v1" or i == len(part) - 1:
            continue
        candidates.append(part[i + 1 :])
    if not candidates:
        return False
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    keys = [secret] if isinstance(secret, str) else list(secret)
    for key in keys:
        mac = hmac.new(key.encode("utf-8"), f"{id}.{ts}.".encode("utf-8") + raw, hashlib.sha256).digest()
        for c in candidates:
            got = _lenient_hex(c)
            if len(got) == len(mac) and hmac.compare_digest(got, mac):
                return True
    return False
