"""``ui.show_more`` — :func:`ui.limit_each` + a "Show more" button.

Reveals the first ``count`` items, then a button that bumps ``count`` by
``step`` — auto-hidden once everything is shown. One primitive owns the
whole reveal-list (rows + button), all client-reactive (no server
round-trip on reveal). Mirrors how :func:`ui.filter_each` owns its rows +
empty state.

    class Reveal(ClientState):
        count: int = field(default=5)

    r = Reveal()
    with ui.vstack(gap="xs"):
        for row in ui.show_more(rows, count=r.count, step=5):
            render_row(row)

``count`` must be a ``ClientBinding`` (it gets incremented). The button
shows only while ``count < len(items)`` and fires ``count += step`` on the
client.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.components.meta.iteration.limit_each import limit_each
from bretzel.render import text
from bretzel.state.scopes.client import ClientBinding


def show_more(
    items: Iterable[Any],
    *,
    count: ClientBinding,
    step: int = 10,
    # ``None`` and not the sentence: a function default is evaluated at
    # the module's IMPORT, so before an app has declared its language.
    label: str | None = None,
    key: str | Callable[[Any], Any] | None = None,
) -> Iterator[Any]:
    """Iterate ``items`` first-``count`` (client-side), then drop a
    "Show more" button after the rows. See the module docstring."""
    from bretzel.components import ui  # lazy : ui namespace is this package

    if not isinstance(count, ClientBinding):
        raise TypeError(
            "show_more: count must be a ClientBinding (it gets incremented) "
            "— for a fixed cap use ui.limit_each instead."
        )

    rows = list(items)  # materialise : the button's auto-hide needs the total
    total = len(rows)

    yield from limit_each(rows, limit=count, key=key)

    # The generator's terminal ``next()`` runs here, inside the caller's
    # container — so the button lands as the list's last child, shown only
    # while hidden rows remain. ``count < total`` is the binding algebra —
    # no hand-built ClientExpression needed.
    more = count < total
    ui.button(
        text("show_more.label") if label is None else label,
        variant="ghost",
        size="sm",
        visible=more,
        on_click=count.increment(step),
    )
