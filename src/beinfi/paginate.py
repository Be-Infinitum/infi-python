"""Handwritten layer (ADR 0055, D3): cursor pagination."""

from __future__ import annotations

from typing import Any, Callable, Iterator, Mapping

from pydantic import BaseModel


def _field(page: Any, name: str, alias: str) -> Any:
    if isinstance(page, Mapping):
        return page.get(alias)
    return getattr(page, name, None)


def paginate(fn: Callable[..., Any], **params: Any) -> Iterator[Any]:
    """Iterates over all items following `nextCursor`.

    `fn` is a list method of the client and `params` are its arguments
    (for example `query={"limit": 50}`)::

        for p in paginate(infi.payments.list, query={"limit": 50}):
            ...
    """
    query = params.pop("query", None)
    if isinstance(query, BaseModel):
        query = query.model_dump(mode="json", by_alias=True, exclude_unset=True)
    base = dict(query or {})
    cursor = base.pop("cursor", None)
    while True:
        q = dict(base)
        if cursor is not None:
            q["cursor"] = cursor
        page = fn(query=q, **params)
        for item in _field(page, "data", "data") or []:
            yield item
        cursor = _field(page, "next_cursor", "nextCursor")
        if not cursor:
            return
