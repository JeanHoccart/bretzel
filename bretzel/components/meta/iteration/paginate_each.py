"""``ui.paginate_each`` — client-side paginated iteration.

Like :func:`ui.each`, but each item's body is wrapped in a ``bz-show`` that
keeps it visible only while its index falls inside the current page window.
Clicking a bound :func:`ui.pagination` re-windows the list **in the
browser** — no server round-trip, no hand-written JS : the framework
derives the window expression, you supply the ``page`` binding and the
``per_page`` size.

    class Pager(ClientState):
        page: int = field(default=1)

    p = Pager()
    with ui.vstack(gap="xs"):
        for row in ui.paginate_each(rows, page=p.page, per_page=10):
            render_row(row)             # row hidden client-side off-window
    ui.pagination(value=p.page, total_pages=math.ceil(len(rows) / 10))

``page`` is **1-indexed** to pair directly with ``ui.pagination`` (whose
``value`` runs 1…total_pages). Item *i* (0-indexed) shows when
``(page-1)*per_page <= i < page*per_page``. ``page`` may also be a plain
``int`` for a fixed window. ``per_page`` is baked at render.

Standalone by design : combining a client-side filter AND pagination needs
the window to count only *matching* rows — a cross-row client computation
this primitive doesn't do. For filter + paginate together, drive both from
server state in an ``@refreshable`` (``sorted(...)[a:b]``), or paginate
the already-filtered server list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.meta.iteration._window import shown_while, window_ref
from bretzel.state.scopes.client import ClientBinding


def paginate_each(
    items: Iterable[Any],
    *,
    page: ClientBinding | int,
    per_page: int,
    key: str | Callable[[Any], Any] | None = None,
) -> Iterator[Any]:
    """Iterate ``items``, showing only the current page's window client-side.

    See the module docstring. ``page`` is a 1-indexed ``ClientBinding`` (or
    a literal ``int``) ; ``per_page`` is the window size (``>= 1``).
    """
    if per_page < 1:
        raise ComponentUsageError("paginate_each: per_page must be >= 1")

    pref = window_ref(page)
    yield from shown_while(
        items, key,
        # (page - 1) * per_page <= index < page * per_page
        lambda index, _: f"{index} >= ({pref} - 1) * {per_page} && {index} < {pref} * {per_page}",
    )
