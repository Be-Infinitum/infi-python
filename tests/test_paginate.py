from beinfi import paginate

PAGES = {
    None: {"data": [1, 2], "nextCursor": "a"},
    "a": {"data": [3], "nextCursor": "b"},
    "b": {"data": [4], "nextCursor": None},
}


def test_follows_next_cursor_until_null_and_passes_filters_on():
    seen = []

    def fn(**params):
        seen.append(params)
        return PAGES[params["query"].get("cursor")]

    assert list(paginate(fn, query={"limit": 2})) == [1, 2, 3, 4]
    assert seen == [{"query": {"limit": 2}}, {"query": {"limit": 2, "cursor": "a"}}, {"query": {"limit": 2, "cursor": "b"}}]


def test_accepts_pydantic_models_and_initial_cursor():
    from beinfi.models import PaymentList

    def fn(query=None, **_):
        c = (query or {}).get("cursor")
        return PaymentList(data=[], nextCursor="x" if c is None else None)

    assert list(paginate(fn)) == []
    calls = []

    def fn2(query=None, **_):
        calls.append(query)
        return {"data": [], "nextCursor": None}

    list(paginate(fn2, query={"cursor": "start"}))
    assert calls == [{"cursor": "start"}]


def test_follows_next_cursor_on_pydantic_pages():
    from beinfi.models import PaymentList

    calls = []

    def fn(query=None, **_):
        c = (query or {}).get("cursor")
        calls.append(c)
        return PaymentList(data=[], nextCursor={None: "a", "a": "b", "b": None}[c])

    assert list(paginate(fn, query={"limit": 10})) == []
    assert calls == [None, "a", "b"]
