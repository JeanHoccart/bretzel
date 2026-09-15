"""``ui.limit_each`` — client-side "first N" iteration.

Like :func:`ui.each`, but each item is wrapped in a ``bz-show`` that keeps
it visible only while its index is below ``limit``. Bumping a bound limit
(e.g. a "Show more" button — see :func:`ui.show_more`) reveals more rows
**in the browser**, no server round-trip.

    class Reveal(ClientState):
        count: int = field(default=5)

    r = Reveal()
    with ui.vstack(gap="xs"):
        for row in ui.limit_each(rows, limit=r.count):
            render_row(row)
    ui.button("Show more", on_click=r.count.increment(5))

``limit`` is a ``ClientBinding`` (reactive) or a plain ``int`` (fixed cap).
Each row carries ``bz-show="index < limit"``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.components.meta.iteration._ref import window_ref
from bretzel.render.iteration import _KEY_STACK, _extract_key
from bretzel.state.scopes.client import ClientBinding, ClientExpression


def limit_each(
    items: Iterable[Any],
    *,
    limit: ClientBinding | int,
    key: str | Callable[[Any], Any] | None = None,
) -> Iterator[Any]:
    """Iterate ``items``, showing only the first ``limit`` client-side.

    See the module docstring. ``limit`` is a ``ClientBinding`` (reactive)
    or an ``int`` (fixed cap).
    """
    from bretzel.components import ui  # lazy : ui namespace is this package

    lref = window_ref(limit)
    for index, item in enumerate(items):
        item_key = _extract_key(item, key, index)
        expr = ClientExpression(f"{index} < {lref}")
        previous = _KEY_STACK.get()
        token = _KEY_STACK.set((*previous, item_key))
        try:
            with ui.vstack(visible=expr, gap="none"):
                yield item
        finally:
            _KEY_STACK.reset(token)
