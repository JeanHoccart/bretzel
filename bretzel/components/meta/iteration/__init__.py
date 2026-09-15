"""Reactive list-iteration family — keyed iteration + filter + paginate.

One discoverable home for the ``*_each`` generators, even though they
straddle two layers by necessity :

- ``each`` est défini **ICI** (``each.py``). Le module
  :mod:`bretzel.render.iteration` ne porte que le key-stack
  (``_KEY_STACK`` / ``current_iteration_key`` / ``_extract_key``), et ne
  définit ni ne ré-exporte ``each``.
- ``filter_each`` / ``paginate_each`` build *on* ``each`` by wrapping each
  item's body in a component (a ``bz-show`` window), so they are
  **component-layer** and live here.

Re-exported together so callers — and the ``ui.*`` namespace — find the
whole family in one place. Future reactive members (e.g. server-side
``sort`` / ``group`` are intentionally NOT here : reorder is a refreshable
concern, cf. ``todo.md``) would join this package.
"""

from bretzel.components.meta.iteration.drag_each import drag_each
from bretzel.components.meta.iteration.each import each
from bretzel.components.meta.iteration.filter_each import filter_each
from bretzel.components.meta.iteration.limit_each import limit_each
from bretzel.components.meta.iteration.paginate_each import paginate_each
from bretzel.components.meta.iteration.show_more import show_more

__all__ = [
    "each",
    "drag_each",
    "filter_each",
    "paginate_each",
    "limit_each",
    "show_more",
]
