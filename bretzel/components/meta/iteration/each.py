"""``ui.each`` — keyed iteration generator (the base of the *_each family).

Iterate items while pushing a stable per-item key onto the render context's
key stack, so components created in the loop body get stable identity (and
survive idiomorph reorders). ``filter_each`` / ``paginate_each`` /
``limit_each`` build on this.

The key-stack machinery itself — ``_KEY_STACK`` / ``current_iteration_key``
/ ``_extract_key`` — lives in :mod:`bretzel.render.iteration` : it's a
render-layer primitive the component base reads for identity, so it stays
below this package in the DAG. ``each`` is just one consumer of it, like
the reactive wrappers sitting next to it here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.render.iteration import _extract_key, key_segment


def each(
    items: Iterable[Any],
    key: str | Callable[[Any], Any] | None = None,
) -> Iterator[Any]:
    """Iterate over items while preserving stable per-item identity."""
    # ``debug=True`` only when a render context is active and asked for it.
    # Lazy import avoids a circular import at module load time.
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    debug = bool(ctx and getattr(ctx.app, "debug", False))

    for index, item in enumerate(items):
        with key_segment(_extract_key(item, key, index, debug=debug)):
            yield item
