"""``ui.filter_each`` — client-side filtered iteration.

Like :func:`ui.each`, but each item's body is wrapped in a ``bz-show`` that
matches a ``query`` ClientBinding against ``text(item)``. Typing in a
bound input filters the list **in the browser** — no server round-trip,
no hand-written JS : the framework derives the match expression, you
supply only the query binding and a per-item text extractor.

    class Filter(ClientState):
        q: str = field(default="")

    f = Filter()
    ui.input(value=f.q, icon_left="search")
    with ui.vstack(gap="xs"):
        for item in ui.filter_each(
            items, query=f.q, text=lambda i: i["name"],
            empty=lambda: ui.empty_state("No match", icon="search"),
        ):
            row(item)                       # row hidden client-side when no match

The match is case-insensitive ``contains`` ; an empty query shows
everything. ``text(item)`` is evaluated at render to fix each row's
searchable string into the generated expression — so the filter never
touches the server.

``empty`` (optional) is a zero-arg callable rendering the "nothing
matched" content — typically ``ui.empty_state(...)``. ``filter_each``
wraps it in its own framework-derived ``bz-show`` (shown only when the
query is non-empty AND no item matches), so the empty state appears and
clears entirely client-side too. One primitive owns the whole filtered
list : the rows *and* their empty state.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.render.iteration import _KEY_STACK, _extract_key
from bretzel.state.scopes.client import ClientBinding, ClientExpression


def _query_js(query: ClientBinding | str) -> str:
    """The lowercased query as a JS sub-expression."""
    if isinstance(query, ClientBinding):
        # ``binding_path()`` is polymorphic (an expression already
        # carries its prefix, a plain binding gets one) — the equivalent
        # of ``Component.path_of`` without importing the component.
        ref = query.binding_path()
    else:
        ref = json.dumps(str(query or ""))
    return f"(({ref}) || '').toLowerCase()"


def filter_each(
    items: Iterable[Any],
    *,
    query: ClientBinding,
    text: Callable[[Any], Any],
    key: str | Callable[[Any], Any] | None = None,
    empty: Callable[[], Any] | None = None,
) -> Iterator[Any]:
    """Iterate ``items``, wrapping each body in a client-side ``bz-show``
    matching ``query`` against ``text(item)``. See module docstring."""
    from bretzel.components import ui  # lazy : ui namespace is this package

    qjs = _query_js(query)
    # Materialise once : the empty-state needs the texts again, and the
    # caller may hand us a one-shot iterator.
    rows = list(items)

    for index, item in enumerate(rows):
        item_key = _extract_key(item, key, index)
        tjs = json.dumps(str(text(item)).lower())
        expr = ClientExpression(f"!{qjs} || {tjs}.indexOf({qjs}) >= 0")
        previous = _KEY_STACK.get()
        token = _KEY_STACK.set((*previous, item_key))
        try:
            with ui.vstack(visible=expr, gap="none"):
                yield item
        finally:
            _KEY_STACK.reset(token)

    # The generator's terminal ``next()`` runs here, still inside the
    # caller's list container — so the empty state lands as the list's
    # last child, shown only when the query excludes every row.
    if empty is not None:
        texts = json.dumps([str(text(i)).lower() for i in rows])
        none_match = ClientExpression(
            f"{qjs} && {texts}.every(function (t) {{ "
            f"return t.indexOf({qjs}) < 0; }})"
        )
        with ui.vstack(visible=none_match, gap="none"):
            empty()
