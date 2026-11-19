"""The rows a table does not rebuild.

A ``ui.table`` (and the ``ui.datatable`` built on it) renders its rows
itself: for each one, the framework calls each column's ``render=`` and
puts the cells together. When an action redraws the list, most rows have
not moved — on the comparison's Helpdesk, changing one ticket's status
rebuilt fifty. So a keyed row is taken back as its last render in this
session gave it when nothing it depends on moved:

- the row itself (a print of its value), the columns (their fields and
  their ``render=``, closures included), the cell classes, the language;
- every field of server state it read, by value.

Taken back, its reads are replayed into the zone being rendered (the
zone keeps following them) and its stamps are made again for this render
(``data-bz-ts`` and ``data-bz-sig``: an ``@idempotent`` handler keys on
them).

A row is not kept when its build left a trace in the request beyond its
reads (a shared part, a state obtained for the first time, a zone of its
own, a header): skipping its build would skip that trace. Nor when it
read a state whole, or when its value or a column has no stable print.

In dev the memo checks instead of serving: the row is rebuilt, and a
difference raises, naming the row — a ``render=`` that reads what the
tracking does not see (the time, a query, a global) would otherwise be
served stale in production, in silence.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass, replace
from typing import Any

from bretzel.core.serialize import serialize
from bretzel.core.tracking import TRACKER, Reads
from bretzel.core.tree import Element, FragmentNode, Node
from bretzel.runtime.protocol import DATA_BZ_SIG, DATA_BZ_TS, posted_action, posted_args
from bretzel.state.scopes.client import ClientState

#: Rows kept for the whole app, every session together, most recent last.
MAX_ROWS = 4096

#: What betrays a print that changes at every render: ``<object at 0x…>``.
_ADDRESS = " at 0x"

#: Where a kept row carries a render's stamp: the path of child indices to
#: the element, and the ``(action id, args blob)`` it signs — ``None`` for
#: a timestamp alone.
_Site = tuple[tuple[int, ...], "tuple[str, str] | None"]


class RowMismatchError(RuntimeError):
    """In dev: a row taken back differs from the row rebuilt."""


@dataclass(frozen=True, slots=True)
class _Kept:
    inputs: tuple[Any, ...]
    values: frozenset[tuple[type, str, str]]
    reads: Reads
    cells: tuple[Node, ...]
    sites: tuple[_Site, ...]


class RowMemo:
    """The rows last rendered, per session. Owned by the application
    (``Bretzel.row_memo``), never by the module; bounded by rows."""

    def __init__(self, max_rows: int = MAX_ROWS) -> None:
        self._rows: OrderedDict[Hashable, Any] = OrderedDict()
        self._max = max_rows

    def get(self, key: Hashable) -> Any:
        kept = self._rows.get(key)
        if kept is not None:
            self._rows.move_to_end(key)
        return kept

    def put(self, key: Hashable, kept: Any) -> None:
        self._rows[key] = kept
        self._rows.move_to_end(key)
        while len(self._rows) > self._max:
            self._rows.popitem(last=False)


def print_of(value: Any) -> str | None:
    """A print of a row's value that two renders of the same data share,
    or ``None`` when there is none (an object that only shows its
    address)."""
    if isinstance(value, dict):
        shown = repr(sorted(value.items(), key=lambda kv: str(kv[0])))
    elif hasattr(value, "keys") and callable(value.keys):  # sqlite3.Row & co.
        try:
            names = value.keys()  # a Row iterates its values, not its names
            shown = repr([(k, value[k]) for k in names])
        except Exception:
            return None
    else:
        shown = repr(value)
    return None if _ADDRESS in shown else shown


def columns_print(columns: Any) -> str | None:
    """A print of the columns: their fields, and each ``render=`` by its
    code, its defaults and what its closure holds."""
    parts = []
    for col in columns:
        render = col.render
        if render is not None:
            code = getattr(render, "__code__", None)
            if code is None:
                return None
            closure = tuple(c.cell_contents for c in (render.__closure__ or ()))
            parts.append((id(code), repr(closure), repr(render.__defaults__)))
        parts.append(repr(replace(col, render=None)))
    shown = repr(parts)
    return None if _ADDRESS in shown else shown


def row_cells(
    ctx: Any,
    row_id: str,
    inputs: tuple[Any, ...],
    build: Callable[[], tuple[Node, ...]],
    values: dict[tuple[type, str], str] | None = None,
) -> tuple[Node, ...]:
    """The cells of the row ``row_id``: taken back when nothing moved, else
    ``build()``.

    ``values``: the field values already read by this table's render,
    shared by its rows — fifty rows read the same few fields, and reading
    them again for each row was most of the memo's own time (20 of 29 ms
    on the Helpdesk's status change). A row's ``render=`` does not write a
    state; if one did, the dev check names it like any impure row."""
    memo = getattr(ctx.app, "row_memo", None)
    if memo is None or not ctx.session_id or None in inputs:
        return build()
    key = (ctx.session_id, row_id)
    kept = memo.get(key)
    if values is None:
        values = {}
    if (kept is not None and kept.inputs == inputs
            and _values_of(kept.reads, values) == kept.values):
        TRACKER.replay(kept.reads)
        cells = _stamped_again(kept, ctx)
        if getattr(getattr(ctx.app, "config", None), "is_dev", False):
            _check(row_id, kept, cells, build)
        return cells
    before = ctx.traces()
    with TRACKER.recording(TRACKER.recording_owner()) as reads:
        cells = build()
    TRACKER.replay(reads)
    read = _values_of(reads, values)
    sites = _sites_of(cells)
    if read is not None and sites is not None and ctx.traces() == before:
        memo.put(key, _Kept(inputs, read, reads, cells, sites))
    return cells


def _check(row_id: str, kept: _Kept, cells: tuple[Node, ...],
           build: Callable[[], tuple[Node, ...]]) -> None:
    with TRACKER.recording(TRACKER.recording_owner()):
        fresh = build()
    if [serialize(c) for c in fresh] != [serialize(c) for c in cells]:
        read = sorted(f"{cls.__name__}.{name}" for cls, name, _ in kept.values)
        raise RowMismatchError(
            f"Row {row_id!r} renders differently with the same row, the same "
            f"columns and the same state ({', '.join(read) or 'no state read'}). "
            "A column's render= depends on something the framework does not follow — "
            "the time, a query, a global — so production would serve this row stale. "
            "Pass that value in the row, or read it from a state."
        )


def _values_of(
    reads: Reads, known: dict[tuple[type, str], str],
) -> frozenset[tuple[type, str, str]] | None:
    """Each server-state field ``reads`` holds, with its value now; ``None``
    when they cannot be compared (a state read whole, an unreadable field).
    ``known``: the values this render has read already, filled here — a
    row whose fields are all known costs a few lookups, no state is
    obtained and nothing is sorted (a set compares without an order)."""
    if reads.whole:
        return None
    out: list[tuple[type, str, str]] = []
    missing: list[tuple[type, str]] = []
    for cls, names in reads.fields.items():
        # A client state renders as a binding: the row's HTML does not
        # depend on its value.
        if issubclass(cls, ClientState):
            continue
        for name in names:
            shown = known.get((cls, name))
            if shown is None:
                missing.append((cls, name))
            else:
                out.append((cls, name, shown))
    if missing:
        instances: dict[type, Any] = {}
        with TRACKER.untracked():
            for cls, name in missing:
                try:
                    if cls not in instances:
                        instances[cls] = cls()
                    shown = known[cls, name] = repr(getattr(instances[cls], name))
                except Exception:
                    return None
                out.append((cls, name, shown))
    return frozenset(out)


def _sites_of(cells: tuple[Node, ...]) -> tuple[_Site, ...] | None:
    """Every place the cells carry a render's stamp, or ``None`` when one of
    them is a signature that cannot be made again (not an action's)."""
    sites: list[_Site] = []
    stack: list[tuple[tuple[int, ...], Node]] = [((i,), cell) for i, cell in enumerate(cells)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, Element) and (DATA_BZ_TS in node.attrs or DATA_BZ_SIG in node.attrs):
            action = posted_action(node.attrs)
            if DATA_BZ_SIG in node.attrs and action is None:
                return None
            sites.append((path, (action, posted_args(node.attrs)) if action else None))
        if isinstance(node, (Element, FragmentNode)):
            stack.extend(((*path, i), kid) for i, kid in enumerate(node.children))
    return tuple(sites)


def _stamped_again(kept: _Kept, ctx: Any) -> tuple[Node, ...]:
    """The kept cells with each stamp made for this render. Rebuilt only
    along the paths that lead to a stamp: a row without one is returned as
    it was kept."""
    cells = list(kept.cells)
    for path, action in kept.sites:
        cells[path[0]] = _restamp(cells[path[0]], path[1:], action, ctx)
    return tuple(cells)


def _restamp(node: Any, path: tuple[int, ...], action: tuple[str, str] | None, ctx: Any) -> Any:
    if path:
        kids = list(node.children)
        kids[path[0]] = _restamp(kids[path[0]], path[1:], action, ctx)
        return replace(node, children=tuple(kids))
    attrs = dict(node.attrs)
    if DATA_BZ_TS in attrs:
        attrs[DATA_BZ_TS] = ctx.render_ts
    if action is not None:
        attrs[DATA_BZ_SIG] = ctx.sign_action(*action)
    return replace(node, attrs=attrs)


__all__ = ["MAX_ROWS", "RowMemo", "RowMismatchError", "columns_print", "print_of", "row_cells"]
