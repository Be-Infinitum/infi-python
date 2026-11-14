"""Handwritten layer (ADR 0055, D3): HTTP transport.

Mirrors src/http.ts of the TypeScript SDK: URL from the key, Bearer, automatic
Idempotency-Key on mutations (the same one across retries), If-Match, X-Infi-Channel,
up to 3 attempts on network error / 429 / 5xx with 0.25s/1s/4s backoff (honoring
Retry-After) and InfiError in the other cases. 4xx is never retried.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Tuple, Union
from urllib.parse import quote

import httpx
from pydantic import BaseModel, TypeAdapter

Channel = Literal["panel", "mcp", "cli", "api"]

SANDBOX_URL = "https://api-sandbox.beinfi.com"
LIVE_URL = "https://api.beinfi.com"
# Seconds between attempts (0.25s, 1s, 4s).
BACKOFF = (0.25, 1.0, 4.0)


class InfiError(Exception):
    """API error (or network error, with status 0 and code `network_error`)."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        tracer_id: Optional[str] = None,
        details: Any = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.tracer_id = tracer_id
        #: Per-field errors (422) or metadata (409), when the server sends them.
        self.details = details
        #: Decoded body of the error response.
        self.body = body

    @property
    def current(self) -> Any:
        """On 412, the current state returned by the server (to show the preview again)."""
        if self.status == 412 and isinstance(self.body, dict):
            return self.body.get("current")
        return None

    def __repr__(self) -> str:
        return f"InfiError(status={self.status!r}, code={self.code!r}, message={self.message!r}, tracer_id={self.tracer_id!r})"


def _first(*values: Any) -> Any:
    """Equivalent of JavaScript's `??`: the first value that is not None."""
    for v in values:
        if v is not None:
            return v
    return None


def parse_error(status: int, text: str) -> InfiError:
    body: Any
    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None
    top: Dict[str, Any] = body if isinstance(body, dict) else {}
    nested_raw = top.get("error")
    nested: Dict[str, Any] = nested_raw if isinstance(nested_raw, dict) else {}
    code = _first(top.get("error_code"), nested.get("code"), f"http_{status}")
    message = _first(top.get("message"), nested.get("message"), text or f"HTTP {status}")
    tracer_id = _first(top.get("tracer_id"), nested.get("request_id"))
    details = _first(top.get("errors"), top.get("metadata"))
    return InfiError(status, code, message, tracer_id, details, _first(body, text or None))


def base_url_for(secret_key: str, api_url: Optional[str] = None) -> str:
    if api_url:
        return api_url.rstrip("/")
    if secret_key.startswith("sk_test_"):
        return SANDBOX_URL
    if secret_key.startswith("sk_live_"):
        return LIVE_URL
    raise ValueError("Infi: secret_key must start with sk_test_ or sk_live_ (or pass api_url)")


def retry_after_seconds(header: Optional[str]) -> Optional[float]:
    if not header:
        return None
    try:
        s = float(header)
        if math.isfinite(s):
            return max(0.0, s)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


@dataclass
class Request:
    method: str
    #: Template with `{param}`, e.g. `/v1/customers/{customerId}`.
    path: str
    path_params: Any = None
    query: Any = None
    headers: Any = None
    body: Any = None
    idempotency_key: Optional[str] = None
    if_match: Optional[str] = None
    channel: Optional[Channel] = None


def _plain(value: Any) -> Any:
    """Pydantic models become a dict with the wire names (alias), only with what was set."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return value


def _text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return ",".join(_text(x) for x in v)
    return str(v)


@lru_cache(maxsize=None)
def _adapter(tp: Any) -> "TypeAdapter[Any]":
    return TypeAdapter(tp)


class Transport:
    def __init__(
        self,
        secret_key: str,
        api_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_attempts: int = 3,
        timeout: float = 60.0,
    ) -> None:
        if not secret_key:
            raise ValueError("Infi: secret_key is required")
        self._secret_key = secret_key
        self._base_url = base_url_for(secret_key, api_url)
        self._client = http_client or httpx.Client(transport=transport, timeout=timeout)
        self._sleep = sleep or time.sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def request(self, spec: Request, responses: Optional[Mapping[int, Any]] = None) -> Any:
        method = spec.method.upper()
        values = _plain(spec.path_params) or {}

        def fill(path: str) -> str:
            out = path
            for key in _placeholders(path):
                if key not in values or values[key] is None:
                    raise ValueError(f"Infi: missing path parameter {key!r} in {spec.path}")
                out = out.replace("{" + key + "}", quote(_text(values[key]), safe="!~*'()"))
            return out

        url = self._base_url + fill(spec.path)
        params: List[Tuple[str, Union[str, int, float, bool, None]]] = [(str(k), _text(v)) for k, v in (_plain(spec.query) or {}).items() if v is not None]
        headers: Dict[str, str] = {"Accept": "application/json", "Authorization": f"Bearer {self._secret_key}"}
        for k, v in (_plain(spec.headers) or {}).items():
            if v is not None:
                headers[k] = _text(v)
        if method not in ("GET", "HEAD"):
            headers["Idempotency-Key"] = spec.idempotency_key or str(uuid.uuid4())
        if spec.if_match is not None:
            headers["If-Match"] = spec.if_match
        if spec.channel:
            headers["X-Infi-Channel"] = spec.channel
        payload: Optional[bytes] = None
        if spec.body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(_plain(spec.body), separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        last_err: Optional[InfiError] = None
        for attempt in range(self._max_attempts):
            last = attempt == self._max_attempts - 1
            try:
                res = self._client.request(method, url, params=httpx.QueryParams(params), headers=headers, content=payload)
            except httpx.TransportError as e:
                last_err = InfiError(0, "network_error", str(e) or "network error")
                if last:
                    raise last_err from e
                self._sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
            text = res.text
            if res.is_success:
                if res.status_code == 204 or text == "":
                    return None
                data = json.loads(text)
                tp = (responses or {}).get(res.status_code)
                return _adapter(tp).validate_python(data) if tp is not None else data
            last_err = parse_error(res.status_code, text)
            retryable = res.status_code == 429 or res.status_code >= 500
            if not retryable or last:
                raise last_err
            wait = retry_after_seconds(res.headers.get("Retry-After"))
            self._sleep(wait if wait is not None else BACKOFF[min(attempt, len(BACKOFF) - 1)])
        assert last_err is not None
        raise last_err


def _placeholders(path: str) -> List[str]:
    out: List[str] = []
    i = 0
    while True:
        a = path.find("{", i)
        if a < 0:
            return out
        b = path.index("}", a)
        out.append(path[a + 1 : b])
        i = b + 1
