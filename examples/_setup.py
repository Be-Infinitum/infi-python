"""Example helpers: sandbox client, step printing and error checks."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable

from pydantic import BaseModel

from beinfi import Infi, InfiError


def setup() -> Infi:
    """A ready-to-use client for a sandbox account that already has an owner.

    The anonymous account (`/public/v1/claimables`) was removed in ADR 0076 and answers 410;
    the key comes from an account created through agent sign-up or the dashboard.
    """
    secret_key = os.environ.get("INFI_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("set INFI_SECRET_KEY to an sk_test_ key from a sandbox account of your own")
    api_url = (os.environ.get("INFI_API_URL") or "").rstrip("/") or None
    return Infi(secret_key, api_url=api_url)


_n = 0


def step(title: str) -> None:
    global _n
    _n += 1
    print(f"\n── {_n}. {title}")


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def show(label: str, value: Any) -> None:
    text = value if isinstance(value, str) else json.dumps(_plain(value), ensure_ascii=False, default=str)
    print(f"   {label}: {text}")


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def uniq() -> str:
    """Short suffix for keys that are unique per run."""
    return str(uuid.uuid4())[:8]


def expect_error(status: int, fn: Callable[[], Any]) -> InfiError:
    """Runs `fn` expecting an InfiError with the given status; fails if it does not come."""
    try:
        fn()
    except InfiError as e:
        if e.status != status:
            raise RuntimeError(f"expected HTTP {status}, got {e.status} ({e.code}): {e.message}") from e
        return e
    raise RuntimeError(f"expected HTTP {status}, but the call succeeded")
