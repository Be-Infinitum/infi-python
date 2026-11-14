"""Infi Python SDK, generated from the public API contract (ADR 0055)."""

from __future__ import annotations

from typing import Callable, Optional

import httpx

from ._generated.resources import Resources
from ._http import Channel, InfiError, Transport
from .paginate import paginate
from .webhooks import verify_webhook

__version__ = "1.0.0"


class Infi(Resources):
    """Client for the Infi public API.

    A `secret_key` with the `sk_test_` prefix talks to the sandbox, `sk_live_` to production;
    `api_url` overrides the URL derived from the prefix.
    """

    def __init__(
        self,
        secret_key: str,
        *,
        api_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_attempts: int = 3,
        timeout: float = 60.0,
    ) -> None:
        self._transport = Transport(
            secret_key,
            api_url=api_url,
            http_client=http_client,
            transport=transport,
            sleep=sleep,
            max_attempts=max_attempts,
            timeout=timeout,
        )
        super().__init__(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "Infi":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["Channel", "Infi", "InfiError", "paginate", "verify_webhook", "__version__"]
