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

from bretzel.render.iteration import _KEY_STACK, _extract_key


def each(
    items: Iterable[Any],
    key: str | Callable[[Any], Any] | None = None,
) -> Iterator[Any]:
    """Iterate over ``items`` while pushing a stable per-item key.

    Use this **instead of** a bare ``for`` loop whenever the body produces
    components with client-side state.

    Parameters
    ----------
    items
        Anything iterable. Lists, generators, querysets, ranges — all work.
    key
        How to extract a stable key per item. Either a callable
        ``(item) -> Any``, or the name of an attribute / dict key. When
        omitted, the cascade in :func:`_extract_key` figures it out.

    Yields
    ------
    The original items, one by one. The iteration key is *not* yielded —
    it lives on the context-var stack for the duration of each
    ``yield`` / resumption.

    Examples
    --------
    Common case, ORM models with ``id`` :

        for user in ui.each(users):
            with ui.card():
                ui.heading(user.name)
                ui.popover(trigger=ui.text(user.name))   # l'état open survit aux réordonnancements

    Custom key extraction :

        for tag in ui.each(tags, key=lambda t: t.slug):
            ui.badge(tag.label)

    Nested loops compose — each inner item gets ``outer_key_inner_key`` :

        for cat in ui.each(categories):
            ui.heading(cat.name)
            for product in ui.each(cat.products):
                ui.product_card(product)
    """
    # ``debug=True`` only when a render context is active and asked for it.
    # Lazy import avoids a circular import at module load time.
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    debug = bool(ctx and getattr(ctx.app, "debug", False))

    for index, item in enumerate(items):
        item_key = _extract_key(item, key, index, debug=debug)

        previous = _KEY_STACK.get()
        token = _KEY_STACK.set((*previous, item_key))
        try:
            yield item
        finally:
            _KEY_STACK.reset(token)
