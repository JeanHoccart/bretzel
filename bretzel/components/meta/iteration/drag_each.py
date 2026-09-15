"""``ui.drag_each`` — iterate items, wrapping each in a ``ui.draggable``.

Same generator shape as :func:`ui.filter_each` : it opens a ``with`` around
the ``yield``, so the caller's body lands inside the wrapper without an
extra indent ::

    with ui.dropzone(name="todo", on_move=reorder):
        for t in ui.drag_each(store.todo, group="task"):
            ui.card(t.title)

It also pushes the item's key onto the iteration stack, exactly as
:func:`ui.each` does — which is what makes ``key=`` optional on
``ui.draggable`` *and* what gives idiomorph the stable identity it needs to
pair a reordered node instead of recreating it.

**Why this exists when ``each`` + ``draggable`` would do.** It saves a line
and an indent level, which on its own would not earn an entry in ``ui.*``.
What earns it is the family : ``each`` / ``filter_each`` / ``limit_each`` /
``paginate_each`` are already the shape app code reaches for, and a drag
list written as the one exception would read as an oversight. The
consistency is the feature.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.render.iteration import _KEY_STACK, _extract_key


def drag_each(
    items: Iterable[Any],
    *,
    group: str | None = None,
    key: str | Callable[[Any], Any] | None = None,
    handle: bool = False,
    disabled: Callable[[Any], bool] | None = None,
) -> Iterator[Any]:
    """Yield each item inside a ``ui.draggable``. See module docstring.

    ``disabled`` is a predicate rather than a flag : which rows can be
    moved is a property of the row (a locked task, a row the reader may
    not touch), so a single boolean for the whole list would be answering
    a different question.
    """
    from bretzel.components import ui  # lazy : ui namespace is this package

    for index, item in enumerate(items):
        item_key = _extract_key(item, key, index)
        previous = _KEY_STACK.get()
        token = _KEY_STACK.set((*previous, item_key))
        try:
            with ui.draggable(
                key=str(item_key),
                group=group,
                handle=handle,
                disabled=bool(disabled(item)) if disabled else False,
            ):
                yield item
        finally:
            _KEY_STACK.reset(token)
