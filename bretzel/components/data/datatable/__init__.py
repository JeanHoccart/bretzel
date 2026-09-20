"""``Datatable`` — public surface of the datatable package.

:class:`~bretzel.state.Query` comes out through this door, the same as
:class:`~bretzel.components.Move` — the type an app handler must **name**
to write its signature (``def load(q: Query)``). It travels with
:func:`apply_query`, which belongs to the component: five of the
repository's six call sites import them on the same line.

:class:`~bretzel.state.datatable.DatatableState` comes out here too, and
it is deliberate: writing a table asks for the component, its state,
``Query`` and ``apply_query``, and it is ONE task. The FILE, for its
part, moved down into ``bretzel/state/datatable/`` on 2026-08-29 — it
depended on nothing of this layer — but moving a file is not moving a
door. It came out of ``from bretzel import DatatableState``, on the top
floor, where it was the only component state.
"""

from bretzel.components.data.datatable.datatable import Datatable, apply_query
from bretzel.components.data.datatable.theme import DATATABLE_THEME
from bretzel.state.datatable import DatatableState, Query

__all__ = [
    "Datatable",
    "DatatableState",
    "DATATABLE_THEME",
    "Query",
    "apply_query",
]
