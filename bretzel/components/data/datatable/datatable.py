"""``Datatable`` — a :class:`~bretzel.components.data.table.Table` that sorts, pages and searches.

Usage ::

    from bretzel.state import DatatableState

    class Issues(DatatableState):
        per_page: int = field(default=25)

    COLUMNS = [
        ui.column("title",  label="Title",  sortable=True),
        ui.column("status", label="Status", sortable=True,
                  render=lambda v, row: ui.badge(v, color="success")),
    ]

    @refreshable
    def issues_table() -> None:
        ui.datatable(state=Issues, columns=COLUMNS, rows=IssueStore().items)

**It assembles, it does not reimplement.** The grid is a composed
``ui.table``, the sort control a composed ``ui.button``, the search box a
composed ``ui.input``, the pager a composed ``ui.pagination``. This module
contributes the query pipeline and the wiring between them — no second
table renderer, no second pager, no client-side engine.

**The query lives on the server.** ``state`` is a
:class:`DatatableState` subclass (one per table), so
``Issues().sort_key`` is readable from any handler. That is what a
browser-side table cannot offer, and it is the reason the CSV export can
replay the exact view the reader is looking at.

**It must sit inside a ``@refreshable``.** No component owns a refresh
zone in Bretzel — clicking a header mutates the state, and the enclosing
zone, which reads that state while the table renders, turns the mutation
into a re-render. One line, and no new framework mechanism.

**The scope is closed** : sort, pagination, global search, per-column
filters, the callable tier and CSV export. Row selection, bulk actions,
inline edit, date filters and range filters are **out of scope**, not
pending work — a datatable is not a
spreadsheet, and whoever needs to slice exports. Inline edit already has
its escape hatch : ``ui.column(render=…)`` takes a component.
"""

from __future__ import annotations

import base64
import dataclasses
import functools
import inspect
import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from typing import Any, ClassVar

from bretzel.components.actions.button import Button
from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component, ComponentUsageError, reactive_prop
from bretzel.components.data.datatable.theme import DATATABLE_THEME
from bretzel.components.data.table import Column, Table, read_cell
from bretzel.components.inputs.combobox import Combobox
from bretzel.components.inputs.input import Input
from bretzel.components.navigation.pagination import Pagination
from bretzel.core.text import fold
from bretzel.core.tree import Element, FragmentNode, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import plural, state_qualname, text
from bretzel.render.context import current_context
from bretzel.render.iteration import key_segment
from bretzel.state import form_value
from bretzel.state.datatable import DatatableState, Query

# A tick-list past this many values stops being a filter and becomes a
# scrolling wall. ``filter=True`` on a free-text column (a name, a title)
# hits it instantly, one distinct value per row. Refused rather than
# shipped, per the same argument as the export guard.
_MAX_FILTER_VALUES = 50

#: The field name of the filter carrier — suffixed by the column key.
#: Carried by the combobox's hidden input, read by :func:`apply_filter`.
_FILTER_FIELD = "bz_dt_filter"

# Form field names for the two controls whose value rides back with the
# action, assembled by :func:`_field`.
_PAGE_FIELD = "bz_dt_page"
_SEARCH_FIELD = "bz_dt_search"

#: The one download endpoint, served by ``server/routing/datatable.py``.
EXPORT_ROUTE = "/_bretzel/datatable.csv"


def _rows_ref(rows_source: Any) -> str:
    """Address the rows callable the same way a handler is addressed."""
    from bretzel.components.base.events import encode_handler_id

    return encode_handler_id(rows_source)


def _encode_export(query: Query, rows_ref: str, rows_args: str,
                   columns: list, filename: str) -> str:
    """Pack what the download endpoint needs into one signed parameter.

    **The QUERY travels, not the state reference.** An export link is a
    plain browser navigation : no ``X-Bretzel-Page-ID`` header, so the
    server cannot resolve the reader's page-scoped state and would read
    a pristine one — exporting the default view while the screen shows a
    filtered one.

    Baking the query in is also free, because the link is re-rendered by
    the same zone refresh that changed the query. It cannot go stale.

    The rest is what the endpoint cannot rediscover : the callable to
    re-run with the arguments a ``partial`` bound to it — the month on
    screen, the account being read —, and the ``(key, label)`` pairs,
    since there is no component left to ask. Signed, so a hand-edited
    ``rows_ref`` cannot point the endpoint at an arbitrary function.
    """
    blob = json.dumps({"q": dataclasses.asdict(query), "r": rows_ref,
                       "a": rows_args, "c": columns, "f": filename},
                      separators=(",", ":"))
    return base64.urlsafe_b64encode(blob.encode()).decode()


def decode_export(payload: str) -> dict:
    """Inverse of :func:`_encode_export`, for the route."""
    return json.loads(base64.urlsafe_b64decode(payload.encode()))


# ───────────────────────────────────────────────────────────────────────────
# State addressing — a class reference that survives the round-trip
# ───────────────────────────────────────────────────────────────────────────


# An action's bound args must be JSON-serialisable, so the state CLASS
# cannot ride along — its address does, encoded by the framework's own
# ``state_qualname``. Spelling ``<module>::<qualname>`` out here would
# be a fourth private copy of ``WIRE_ID_SEP`` : the decoder
# (``resolve_handler``) splits on the shared constant, so a local copy
# desynchronises the two halves the day it moves — and the symptom is a
# sort button that silently stops working.


def _field(prefix: str, state_cls: type[DatatableState]) -> str:
    """Form field name for one of this table's controls.

    Suffixed with the state's class name so two Datatables on one page
    never read each other's submission. Written ONCE : the emitter and
    the handler that reads it back have to agree, and a format spelled
    out at both ends is the same silent-failure shape as a hand-rolled
    wire id.
    """
    return f"{prefix}__{state_cls.__name__}"


def _resolve_state(ref: str) -> DatatableState:
    """Resolve a ``_state_ref`` back to a live state instance.

    Deferred import : ``server`` sits ABOVE ``components`` in the load
    DAG, so this may not be a module-level import. It runs at request
    time, inside a handler, which is exactly what the charter's
    "deferred imports" escape hatch is for. Reused rather than
    re-implemented — ``resolve_handler`` already is the framework's one
    ``sys.modules`` walk, and a State subclass is callable, which is all
    it requires of its target.
    """
    from bretzel.server.handlers import resolve_handler

    return resolve_handler(ref)()


# ───────────────────────────────────────────────────────────────────────────
# Action handlers — module-level so they resolve through sys.modules
# ───────────────────────────────────────────────────────────────────────────


def sort_by(state_ref: str, key: str) -> None:
    """Advance the sort on ``key`` — bound per column by the header button."""
    _resolve_state(state_ref).cycle_sort(key)


def go_to_page(state_ref: str) -> None:
    """Move to the page the pager just submitted."""
    state = _resolve_state(state_ref)
    raw = form_value(_field(_PAGE_FIELD, type(state)))
    try:
        state.page = max(1, int(raw))
    except (TypeError, ValueError):
        # A page number that isn't one means a tampered or malformed
        # submission ; ignoring it beats raising a 500 on a pager click.
        return


def search_for(state_ref: str) -> None:
    """Apply the search box's current text, and go back to page 1.

    Staying on page 4 while the result set shrinks under you shows an
    empty table and reads as a bug.
    """
    state = _resolve_state(state_ref)
    state.search = (form_value(_field(_SEARCH_FIELD, type(state))) or "").strip()
    state.page = 1


def apply_filter(state_ref: str, key: str, domain: list) -> None:
    """Commit one column's selection — fired when its panel CLOSES.

    The reader ticks freely with no round-trip ; this runs once, on the
    way out. The picks arrive as the combobox's hidden input (a JSON
    array) rather than as bound args, because they are chosen client-side
    long after the action was signed.

    The panel ticks what to SHOW : nothing ticked is no filter at all,
    the way every tick-list filter reads (a fresh panel opens empty, not
    with every value pre-ticked) — ``set_filter``'s rule. ``domain``
    rides in the bound args : ``set_filter`` keeps the picks in domain
    order and drops the filter when they cover it all, and the server
    cannot re-derive it in the callable tier, where it holds no rows.
    """
    state = _resolve_state(state_ref)
    raw = form_value(f"{_field(_FILTER_FIELD, type(state))}__{key}")
    if raw is None:
        return
    try:
        picked = [str(v) for v in json.loads(str(raw) or "[]")]
    except (ValueError, TypeError):
        # A malformed carrier means a tampered or half-written submission.
        # Ignoring it beats a 500 on closing a panel.
        return
    state.set_filter(key, picked, list(domain))


def clear_filters(state_ref: str) -> None:
    """Drop every column filter — the toolbar's reset."""
    _resolve_state(state_ref).clear_filters()


# ───────────────────────────────────────────────────────────────────────────
# The query pipeline — pure, so it can be tested without a render context
# ───────────────────────────────────────────────────────────────────────────


#: The search form — the framework's one ``fold`` (``bretzel/core/text.py``),
#: the same a combobox and ``filter_each`` compare.
_fold = fold


def _sort_bucket(value: Any) -> tuple[int, float, str]:
    """Order key for one cell, total over mixed types.

    Python refuses to compare an ``int`` with a ``str``, and a real table
    column holds both often enough (a blank cell, a "N/A"). So each value
    lands in a numbered bucket first and is only compared within it :
    numbers before text, and *never* against it.

    ``bool`` is checked before ``int`` on purpose — it is a subclass, and
    sorting True/False as 1/0 among real numbers reads as noise.

    TextNode is compared with its accents folded away. ``casefold`` alone
    leaves ``é`` at code point 0xE9, i.e. AFTER ``z`` — so a column of
    French names puts every accented one at the bottom, which reads as a
    broken sort rather than as a collation subtlety. Folding to the base
    letter gets ``Émilie`` between ``Alan`` and ``Grace``, where a reader
    expects it, without pulling in a locale dependency.
    """
    if isinstance(value, bool):
        return (1, 0.0, str(value))
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    return (1, 0.0, _fold(str(value)))


def _column_counts(rows: Sequence[Any],
                   keys: Sequence[str]) -> dict[str, Counter[str]]:
    """How many rows of ``rows`` take each value, for every column of ``keys``.

    The number a filter panel shows next to each value. Counted on the
    FULL source, never on the current page or the current filter — a
    value you just unticked has to stay in the list with its weight, or
    you could not tell what ticking it back would bring.

    ONE pass over the rows for all the columns : this walks EVERY row of
    the source on every render.
    """
    counts = {key: Counter[str]() for key in keys}
    if not counts:
        return counts
    # Dict branch hoisted out of the loop : ``read_cell``'s isinstance +
    # call would otherwise run per cell.
    read = ((lambda row, key: row.get(key)) if rows and isinstance(rows[0], dict)
            else read_cell)
    for row in rows:
        for key, counter in counts.items():
            counter[str(read(row, key))] += 1
    return counts


def apply_query(
    rows: Sequence[Any],
    columns: Sequence[Column],
    query: Query,
) -> tuple[list[Any], int]:
    """Run ``query`` over ``rows`` : filter → search → sort → page.

    Returns ``(page_rows, total_matched)`` — the slice to render and the
    count *after* narrowing, which is what the footer and the pager both
    need.

    Order matters. Narrowing first means the result count reflects what
    the reader sees ; paging last means the window applies to the final
    ordering rather than to the source list. ``for_export`` skips the
    window entirely — a CSV of the visible page is not what anyone means
    by "export".
    """
    keys = [c.key for c in columns if c.key]
    # NOT ``list(rows)`` : nothing below mutates in place (filter, sort
    # and slice each build a new list), so a defensive copy would be a
    # full extra pass over the source on every render.
    result = rows

    if query.filters:
        result = [
            row for row in result
            if query.matches_filters(functools.partial(read_cell, row))
        ]

    if query.search:
        # Folded, like the sort — searching "emilie" must find "Émilie".
        # Shipping accent-insensitive sorting next to accent-SENSITIVE
        # search inside one component is the kind of split nobody can
        # explain to a reader.
        needle = _fold(query.search)
        result = [
            row for row in result
            if any(needle in _fold(str(read_cell(row, k) or "")) for k in keys)
        ]

    total = len(result)

    # Hoisted out of both loops on purpose : ``sort_key`` is a State
    # Field DESCRIPTOR, not an attribute — every read goes through
    # dependency tracking. Read per row per pass it would cost 2N+1
    # tracked reads, and the first one already registers the dependency,
    # so the rest would be pure overhead.
    sort_key = query.sort_key
    if sort_key:
        # Empty cells sort to the END in both directions — a column of
        # blanks is never what someone clicked a header to see. Achieved
        # by partitioning rather than by a sort key, since ``reverse=True``
        # would otherwise flip the blanks to the front.
        filled, blanks = [], []
        for row in result:
            value = read_cell(row, sort_key)
            (blanks if value is None or value == "" else filled).append(row)
        filled.sort(
            key=lambda row: _sort_bucket(read_cell(row, sort_key)),
            reverse=query.descending,
        )
        result = filled + blanks

    if query.for_export:
        return list(result), total
    start = query.offset
    # Materialised here rather than up front : ``rows`` is only typed as
    # a Sequence, and slicing a non-list would return a non-list.
    return list(result[start:start + query.per_page]), total


# ───────────────────────────────────────────────────────────────────────────
# Component
# ───────────────────────────────────────────────────────────────────────────


class Datatable(Component):
    """Table with server-driven sort, pagination and search."""

    THEME: ClassVar[dict[str, Any]] = DATATABLE_THEME
    THEME_KEY: ClassVar[str] = "datatable"
    #: Like ``Table``, more markedly so: the query pipeline searches,
    #: filters, sorts and paginates before anything at all is rendered.
    #: Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    #: ``item_click`` is DECLARED, even though this component does not
    #: wire it itself: it passes ``on_item_click=`` to the ``Table`` it
    #: renders, which routes it through ``item_action_attrs``. The three
    #: shapes of an ``on_*`` therefore work here as there — a server
    #: callable, a client expression string, or a list of both.
    #:
    #: ⚠️ NOT declaring it would make nothing inert, it would make the
    #: introspected surface WRONG: ``bretzel describe datatable`` reads
    #: ``EVENTS``, and would say "no event" of a component that accepts one.
    #: The base layer, for its part, never sees this handler go by — it
    #: is a named parameter of the ``__init__``, not a ``**kwargs`` — so
    #: the declaration re-wires nothing on the root.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    # Every axis is server-driven : a click mutates the state, the
    # enclosing @refreshable re-renders with the new query baked in.
    # There is no client driver for any of it, so nothing is bindable.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        state: type[DatatableState],
        columns: Iterable[Column] = (),
        rows: Iterable[Any] | Callable[[Query], tuple[Any, int]] = (),
        search: bool = True,
        search_placeholder: str | None = None,
        exportable: bool = False,
        export_filename: str = "export.csv",
        max_height: str | None = None,
        row_key: str | Callable[[Any], Any] | None = None,
        on_item_click: Callable[..., Any] | None = None,
        size: str | None = None,
        color: str | None = None,
        empty_text: str | Component | None = None,
        empty_icon: str | Component | None = "inbox",
        empty_description: str | Component | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(size=size, color=color, **kwargs)
        self._state_cls = _check_state(state)
        self._columns = list(columns)
        # Captured before the flag is spent — cf. ``_head_title``. A column
        # with no key has nothing to sort BY, so it can't be in here.
        self._sortable_keys = {c.key for c in self._columns if c.sortable and c.key}
        # ``rows`` is either the data (we run the pipeline) or a callable
        # that runs it for you. Kept unresolved here : the callable must
        # not run at construction, only when the query is known.
        self._rows_source = rows if callable(rows) else None
        self._rows = [] if callable(rows) else list(rows)
        # Domains captured HERE, from the original declarations, and
        # AFTER ``_rows`` exists. Table receives the columns with both
        # flags spent, so anything read back from ``col`` inside
        # ``head_render`` says ``filter=False`` — the same trap
        # ``_sortable_keys`` exists for, and it cost a silently empty
        # popover before the export test caught it.
        # The rows per value, shown in each panel. Only the list tier
        # can count : a callable hands back one page, not the source.
        self._filter_counts: dict[str, Counter[str]] = (
            {} if self._rows_source is not None else _column_counts(
                self._rows, [c.key for c in self._columns if c.filter and c.key],
            )
        )
        self._filter_domains = {
            c.key: self._domain_of(c) for c in self._columns
            if c.filter and c.key
        }
        self._search = search
        self._search_placeholder = search_placeholder
        self._exportable = _check_exportable(exportable, self._rows_source)
        self._export_filename = export_filename
        self._max_height = max_height
        self._row_key = row_key
        self._item_click = on_item_click
        self._empty_text = empty_text
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty
        self._check_refresh_zone()

    def _domain_of(self, col: Column) -> list[str]:
        """The tick-list for one filterable column.

        A declared domain wins and is the ONLY option in the callable
        tier : the component holds no rows there, so it cannot discover
        what values exist. Saying so out loud beats rendering a popover
        with nothing in it.
        """
        if isinstance(col.filter, tuple):
            return _check_domain(col, list(col.filter))
        if self._rows_source is not None:
            raise ComponentUsageError(
                f"ui.datatable: column {col.key!r} uses filter=True, but "
                "rows= is a callable — the component holds no rows, so it "
                "cannot discover which values exist. State them: "
                f'ui.column("{col.key}", filter=["a", "b"]).'
            )
        # Folded sort, so the tick-list doesn't dump every accented value
        # after Z — the same complaint the row sort exists to answer.
        return _check_domain(col, sorted(
            (v for v in self._filter_counts[col.key] if v not in ("", "None")),
            key=_fold,
        ))

    # ── Construction-time guards ───────────────────────────────────────

    def _is_interactive(self) -> bool:
        """Whether this table has a control that mutates its state.

        A table with no control at all is a display table with extra
        chrome — it never posts, so it has nothing to re-render and needs
        no zone.

        Enumerating the control sources is the fragile part, and it has
        already cost twice : filters and the callable tier both shipped
        without being added here, so a filterable table with no search
        and no sortable column skipped the guard entirely. Anything that
        renders a control must be listed.
        """
        if self._search or self._sortable_keys or self._filter_domains:
            return True
        if self._rows_source is not None:
            # The callable tier holds no rows locally, so the page-count
            # test below is blind there — and it is exactly the tier that
            # paginates large sets.
            return True
        return len(self._rows) > max(1, self._state_cls().per_page)

    def _check_refresh_zone(self) -> None:
        """Refuse to render a control nobody will re-render.

        This is THE failure mode of a server-driven table : the header
        posts, ``cycle_sort`` runs, the state changes — and the page
        stays exactly as it was, because no ``@refreshable`` zone
        encloses the table. Nothing errors, nothing logs ; the reader
        just clicks a header that does nothing.

        So the check runs at construction, while the enclosing zone is
        still on the parent stack, and names both the state and the fix.
        Inside a zone, the zone follows the state by itself: the table
        reads it while it renders.
        """
        if not self._is_interactive():
            return

        from bretzel.render import maybe_current_context

        ctx = maybe_current_context()
        if ctx is None:  # test rig with no context — nothing to check
            return
        if self._zone is not None:
            return

        name = self._state_cls.__name__
        raise ComponentUsageError(
            f"ui.datatable(state={name}) is not inside a @refreshable zone. "
            f"Sorting, paging and searching all work by mutating {name} — "
            "with no zone around the table, the controls would post and the "
            "page would never change. Wrap it :\n"
            "    @refreshable\n"
            "    def my_table() -> None:\n"
            f"        ui.datatable(state={name}, ...)"
        )

    def _size_map(self) -> dict[str, str]:
        """The composed children's size tokens for this table's ``size``
        (its slot classes reach the slots through ``compose_class``)."""
        return self._size_row() or {}

    # ── Header ─────────────────────────────────────────────────────────

    def _head_title(self, col: Column) -> Any:
        """Build one header : the sort control, or a plain label.

        Filters live in the toolbar : a header is for reading the column
        name and ordering by it, and hanging a second control off it would
        make every filterable column wider and the free-text one narrower.
        This IS the ``head_render=`` seam.
        """
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # Read from the ORIGINAL declaration, not from ``col.sortable`` :
        # Table receives the columns with the flag already spent (it
        # rejects it), so by the time it calls back here every column
        # says ``sortable=False``.
        if col.key not in self._sortable_keys:
            return (
                Element(
                    tag="span",
                    attrs={"class": slots.get("head_static", "")},
                    children=(TextNode(col.label),),
                )
                if col.label
                else None
            )

        state = self._state_cls()
        active = state.sort_key == col.key
        icons = theme.get("sort_icons", {})
        return Button(
            col.label,
            # ``ghost`` is right HERE and nowhere else in this component :
            # the ``<th>`` already draws the box (Table tints its header
            # row), so the button only has to contribute the hit area and
            # the affordances a bare cell lacks. The toolbar has no such
            # container, which is why its controls are ``soft`` — cf.
            # ``_column_filter``.
            variant="ghost",
            # ``current`` at rest so a sortable header is the SAME colour as
            # the plain header beside it; skipping it makes one
            # header row read half accent-blue, half muted grey, with the
            # split following nothing the eye can interpret. The accent is
            # spent on the ACTIVE column only, where it means something.
            # ⚠️ It is NOT the "colour of an embedded subcomponent"
            # convention: that one speaks of a subordinate component
            # inheriting its parent's ink, and it precisely files Button
            # among the exceptions.
            # The rule applied here is ``components.md`` § "the accent
            # marks the ACTIVE peer".
            color=(self._reactive_values.get("color") or "primary")
            if active else "current",
            # Constant on purpose, and baselined in
            # ``test_child_component_size_is_not_frozen`` with the reason :
            # the header type scale is Table's and does not move with
            # ``size=``, so a sortable header must not move either or it
            # stops matching the plain header next to it. Cf. theme.py.
            size="xs",
            icon_right=icons.get(state.sort_dir if active else "", ""),
            classes=" ".join(filter(None, (
                slots.get("head_button", ""),
                theme.get("head_button_aligns", {}).get(col.align, ""),
            ))),
            on_click=functools.partial(
                sort_by, state_qualname(self._state_cls), col.key
            ),
            # Read by the probes and by anyone debugging a sort that
            # doesn't stick — the DOM says which column is active.
            attrs={"data-sort": state.sort_dir if active else "none"},
        )

    def _column_filter(self, col: Column, *, colour: str,
                     slots: dict[str, str],
                     sizes: dict[str, str]) -> Component:
        """One toolbar filter : the column's label, its count, its panel.

        **It IS a ``ui.combobox``**, not a look-alike. The multi-pick
        combobox already ships every piece this needs — an anchored
        panel, a tickable option list, a search field, a header bar with
        a ``N / total`` counter and Select-all / Clear — all wired to one
        client scope and one hidden input. Rebuilding that out of a
        Popover, a VStack, N Checkboxes and two IconButtons was ~90 lines
        maintaining a second copy of a widget the framework already owns,
        and it drifted from it on every detail nobody looked at twice :
        the option padding, the panel width, the size scale of the search
        box, the wording of the two commands.

        ``trigger=`` is what lets the two shapes meet. A combobox is
        driven by TYPING (the search field is its trigger) ; a filter is
        OPENED and then ticked. The slot hands the opening gesture to
        this button and moves the search field into the panel — same
        panel, same list, same commands, different way in.

        **Nothing is applied while the panel is open.** The picks live in
        the combobox's own client scope, so ticking costs no round-trip
        and the table does not jump under the reader mid-decision ; ONE
        action fires on ``close``, reading the final selection off the
        hidden input the combobox already renders.

        **The ticks say what to show, and none means all.** The panel
        opens empty on an unfiltered column — no "Select all" to offer,
        since ticking everything and ticking nothing are the same view.
        The combobox's filter shape does the rest : checkboxes, Clear
        once something is ticked, a search field only on a long list.
        """
        state = self._state_cls()
        ref = state_qualname(self._state_cls)
        domain = self._filter_domains.get(col.key, [])
        kept = state.filters.get(col.key)
        narrowed = kept is not None
        picked = list(kept or ())
        counts = self._filter_counts.get(col.key)
        # Stable per (table, column) : the combobox scopes its own
        # ``hx-include`` by this id (so the close action carries the
        # picks), and idiomorph keeps matching the same node across
        # refreshes.
        box_id = f"bzf_{self._state_cls.__name__}_{col.key}"

        label = col.label or col.key
        if not narrowed:
            caption = label
        elif len(picked) <= 2:
            # Two names still fit a toolbar button ; past that, a count.
            caption = f"{label} · {', '.join(picked)}"
        else:
            caption = f"{label} · {len(picked)}"
        return Combobox(
            domain,
            id=box_id,
            value=picked,
            multiple=True,
            render=(
                None if counts is None
                else functools.partial(_value_with_count, counts,
                                       slots.get("filter_count", ""))
            ),
            name=_field(_FILTER_FIELD, self._state_cls) + f"__{col.key}",
            # Distinct from ``search_placeholder=``, which describes the global
            # search: in a panel it would name the wrong list — there you
            # search column VALUES, not rows.
            placeholder=text("datatable.filter_placeholder"),
            color=colour,
            size=sizes.get("toolbar_size", "sm"),
            trigger=Button(
                caption,
                # ``soft`` IN BOTH STATES, and it is the COLOUR that
                # says which.
                #
                # Not ``ghost``: its box only exists under
                # ``not-disabled:hover:``, so at rest it is text, and a
                # toolbar is a place where you must SEE what is pressable
                # before pressing it. It is the rule
                # ``theme/tailwind.py`` writes in black and white at the
                # end of its note on ``@custom-variant hover``:
                # "``hover:`` must still never CARRY an affordance". It
                # holds everywhere, not only for the finger — a ghost's
                # box IS its affordance. (A ``ui.button(variant="ghost")``
                # is still right INSIDE a container that already draws
                # the box: cf. ``_head_title``, where the ``<th>``
                # carries it.)
                #
                # And a SINGLE variant for both states because changing
                # variant changes the box: the bar jumped at the first
                # filter set. The tone changes, the geometry does not.
                variant="surface",
                # The "the accent marks the ACTIVE peer" convention —
                # cf. ``components.md`` § of the same name.
                color=colour if narrowed else "current",
                size=sizes.get("toolbar_size", "sm"),
                icon_left="list-filter",
            ),
            on_close=functools.partial(apply_filter, ref, col.key, domain),
        )

    def _export_link(self, *, slots: dict[str, str],
                     sizes: dict[str, str]) -> Node:
        """The CSV button — a real link, not an action.

        A download cannot ride the action pipeline : the response has to
        be the file, and HTMX would try to swap it into the page. So it
        is a plain signed GET, and its ``download`` attribute keeps htmx
        off it.
        """
        from bretzel.server.handlers import encode_args, sign_action

        columns = [[c.key, c.label] for c in self._columns if c.key]
        payload = _encode_export(
            self._state_cls().to_query(for_export=True),
            _rows_ref(self._rows_source), encode_args(self._rows_source),
            columns, self._export_filename,
        )
        context = current_context()
        key = getattr(getattr(context.app, "config", None), "_action_key", b"")
        sig = sign_action(key, EXPORT_ROUTE, payload,
                          session_id=context.session_id) if key else ""
        # A composed ``ui.button`` retagged as an anchor, NOT a ``ui.link``.
        # The control sits next to "Clear filters" in the same toolbar, so
        # it has to be the same object — a link rendered as a link reads
        # as body text that wandered into a control strip, underlined and
        # a different height. ``tag="a"`` is the universal retag kwarg, so
        # this is the actual Button, with the actual button classes, that
        # happens to be an anchor because only an anchor can download.
        # ``type`` is set to the MIME type it means on an anchor — Button
        # stamps ``type="button"``, which is meaningless there.
        button = Button(
            text("datatable.export_csv"),
            tag="a",
            classes=slots.get("export", ""),
            variant="surface",
            size=sizes.get("toolbar_size", "sm"),
            color="current",
            icon_left="download",
            href=f"{EXPORT_ROUTE}?q={payload}&sig={sig}",
            attrs={
                "download": self._export_filename,
                "type": "text/csv",
            },
        )
        return Component.render_detached(button)

    def _fetch(self, query: Query) -> tuple[list[Any], int]:
        """``(rows, total)`` for ``query`` — from the list or the callable.

        The two tiers meet here and nowhere else, so everything
        downstream (render, export) is written once against one shape.
        """
        if self._rows_source is None:
            return apply_query(self._rows, self._columns, query)
        result = self._rows_source(query)
        if inspect.isawaitable(result):
            # ``render()`` is synchronous — it cannot await. Say so with
            # the fix rather than let ``rows, total = <coroutine>`` fail
            # three frames deep with "cannot unpack non-iterable
            # coroutine object". The export route CAN await, so the
            # asymmetry is real and worth naming.
            result.close()
            raise ComponentUsageError(
                "ui.datatable: rows= returned a coroutine, but render() is "
                "synchronous and cannot await it. Make the callable a "
                "plain `def` — do the awaiting in the handler or zone that "
                "loads the data, and hand the datatable the result."
            )
        rows, total = result
        return list(rows), int(total)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        """Everything the table builds is born under its STATE's identity.

        Without that, the pager, the search and the bar's buttons are
        built during ``render()`` — so with no parent on the stack — and
        get a **positional, page-global** id: ``root_pagination_0`` for
        the first table, ``root_pagination_1`` for the second. Yet a zone
        re-renders ALONE: the generator starts from zero and the second
        table returns ``root_pagination_0``, that is to say the FIRST
        one's id.

        Without the key, on two tables of one page ::

            before the click: ['root_pagination_0', 'root_pagination_1']
            click page 5 on B
            after the click:  ['root_pagination_0', 'root_pagination_0']

        ``bz-id`` being idiomorph's pairing key AND ``scope.absorb``'s,
        B's pager then adopts A's scope — so its ``_total`` — and shows
        A's page count; then A's hidden input sees its value change and
        POSTs in its turn. **One click, two requests**, and the wrong
        table navigating.

        The key is the state class's name, not ``self.id``: the table's
        id is positional too, so unstable between a full render and a
        zone render. The state's name, for its part, is the same on both
        sides — it is already the identity ``_field()`` and
        ``bzf_<State>_<column>`` use. Two static tables sharing a class
        are still told apart by ``IdGenerator``'s sibling counter
        (``…_1``, ``…_2``), which gives them back their old positional
        behaviour — they never re-render partially, so that is correct.
        """
        with key_segment(self._state_cls.__name__):
            return self._render_tree()

    def _render_tree(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        modifiers = theme.get("modifiers", {})

        sizes = self._size_map()
        state = self._state_cls()
        ref = state_qualname(self._state_cls)
        color = self._reactive_values.get("color") or "primary"
        size = self._reactive_values.get("size") or "md"

        page_rows, total = self._fetch(state.to_query())
        per_page = max(1, state.per_page)
        total_pages = max(1, math.ceil(total / per_page))

        children: list[Node] = []

        # ── Toolbar ─────────────────────────────────────────────────
        # Rendered whole, always, never as an empty ``hx-preserve`` shell.
        # The zone diff (``render/zone_diff.py``) makes such a shell
        # useless — an unchanged bar is byte-identical, so it is not
        # shipped — and harmful: the diff would ship the SHELL alone, as
        # its own out-of-band morph, and htmx honours ``hx-preserve``
        # inside a swapped fragment, not on the element it morphs. The bar
        # would become an empty div at the first sort, and the diff,
        # believing the client holds that shell, would never send it back.
        # Gate: tests/runtime_js/test_a_datatable_keeps_its_toolbar.py.
        toolbar_id = f"bzdt_{self._state_cls.__name__}_toolbar"
        if self._has_toolbar(state):
            children.append(self._toolbar_node(
                toolbar_id=toolbar_id, state=state, ref=ref,
                color=color, slots=slots, sizes=sizes,
            ))

        # ── The table itself ────────────────────────────────────────
        table_classes = modifiers.get("sticky", "") if self._max_height else ""
        table = Table(
            # Both Datatable-only flags are consumed HERE (they built the
            # header controls) ; Table rejects them unconditionally, so
            # what it receives is the same column list, flags spent.
            columns=[replace(c, sortable=False, filter=False)
                     for c in self._columns],
            rows=page_rows,
            row_key=self._row_key,
            on_item_click=self._item_click,
            size=size,
            color=color,
            empty_text=self._empty_text,
            empty_icon=self._empty_icon,
            empty_description=self._empty_description,
            empty=self._empty,
            head_render=self._head_title,
            classes=table_classes,
            style=f"max-height: {self._max_height}" if self._max_height else None,
        )
        # `debounce=` / `throttle=` set on the datatable apply to the
        # ROW click, which is rendered by the inner Table. The base layer
        # has already translated them into a trigger modifier on THIS
        # instance; the raw milliseconds, for their part, have been
        # consumed. So we forward the modifier, not the kwarg — otherwise
        # the delay is accepted then lost, which
        # `test_trigger_modifiers_survive` checks.
        table._trigger_modifier = self._trigger_modifier
        children.append(Component.render_detached(table))

        # ── Footer ──────────────────────────────────────────────────
        info_class = self.compose_class("footer_info")
        # Always rendered when there is anything to count : the result
        # total is the only feedback that a search actually narrowed
        # something, and it must not vanish when the pager does.
        footer: list[Node] = [
            Element(
                tag="div",
                attrs={"class": info_class},
                children=(TextNode(_result_label(
                    total,
                    None if self._rows_source is not None
                    else len(self._rows),
                )),),
            )
        ]
        if total_pages > 1:
            pager = Pagination(
                value=min(max(1, state.page), total_pages),
                total_pages=total_pages,
                color=color,
                size=sizes.get("pager", "sm"),
                name=_field(_PAGE_FIELD, self._state_cls),
                on_change=functools.partial(go_to_page, ref),
            )
            footer.append(Component.render_detached(pager))
        children.append(
            Element(
                tag="div",
                attrs={"class": slots.get("footer", "")},
                children=tuple(footer),
            )
        )

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("root", "")
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

    def _has_toolbar(self, state: DatatableState) -> bool:
        """Does this table have a toolbar at all?

        The four terms are exactly those :meth:`_toolbar_node` knows how
        to render: no control, no bar — not even an empty ``<div>``.

        ``state.filters`` is one of them because the "Clear filters"
        button only exists when something filters — a table with no other
        control therefore gains a bar at the first filter set.
        """
        return bool(
            self._search
            or self._filter_domains
            or self._exportable
            or state.filters
        )

    def _toolbar_node(
        self, *, toolbar_id: str, state: DatatableState, ref: str,
        color: str, slots: dict[str, str], sizes: dict[str, str],
    ) -> Node:
        """The full toolbar.

        Called only when :meth:`_has_toolbar` is true.
        """
        tools: list[Node] = []
        if self._search:
            tools.append(Component.render_detached(Input(
                value=state.search,
                name=_field(_SEARCH_FIELD, self._state_cls),
                placeholder=(text("datatable.search") if self._search_placeholder is None
                             else self._search_placeholder),
                icon_left="search",
                # Clearing the search from the keyboard asks for a
                # select-all followed by a delete; the cross does it in
                # one gesture and leaves with the `change`, so the server
                # drops the search without anything to re-wire here.
                clearable=True,
                size=sizes.get("toolbar_size", "sm"),
                classes=self.compose_class("search"),
                on_change=functools.partial(search_for, ref),
            )))
        # Only offered once something IS filtered : a permanently visible
        # "Clear filters" is a button that does nothing most of the time.
        if state.filters:
            tools.append(Component.render_detached(IconButton(
                "filter-x",
                # An ICON, not "Clear filters" spelled out: this
                # control only appears WHEN something filters, so it adds
                # width exactly when the bar is at its fullest — it is
                # what pushed the export onto the next line. The icon
                # renders ~78 px onto the line.
                #
                # `error` and not the ambient ink: it is the bar's only
                # control that UNDOES something, and an icon has no text
                # to say it in its place. Same intent as the filter
                # panel's "Clear", whose theme turns to error
                # (`footer_btn_muted`). Not `primary`: the accent is
                # reserved for the ACTIVE filter (cf. `components.md`
                # § "the accent marks the ACTIVE peer"), and a reset is
                # not a state to signal.
                variant="surface", color="error",
                size=sizes.get("toolbar_size", "sm"),
                tooltip=text("datatable.clear_filters"),
                aria_label=text("datatable.clear_filters"),
                on_click=functools.partial(clear_filters, ref),
            )))
        # One pill per filterable column, in column order and labelled by
        # the column — which is why the filter is declared on the column
        # and nowhere else. They sit NEXT TO the search box because that
        # is where a reader looks to narrow a list.
        for col in self._columns:
            if col.key in self._filter_domains:
                tools.append(Component.render_detached(
                    self._column_filter(col, colour=color, slots=slots,
                                        sizes=sizes)
                ))
        if self._exportable:
            tools.append(self._export_link(slots=slots, sizes=sizes))
        return Element(
            tag="div",
            attrs={
                # The zone diff's target: an addressed node is diffed and
                # shipped on its own, so an unchanged bar stays out of the
                # response.
                "id": toolbar_id,
                "class": slots.get("toolbar", ""),
            },
            children=tuple(tools),
        )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _check_exportable(exportable: bool, rows_source: Any) -> bool:
    """Refuse ``exportable=True`` over an in-memory row list.

    A CSV has to contain every matching row, not the twenty on screen —
    so the download endpoint has to re-run the query, out of band, long
    after the render that built ``rows=`` threw the list away. A callable
    is the only shape the server can invoke again.

    Raising rather than quietly hiding the button : a missing export
    button is exactly the kind of thing you notice in production, on a
    Friday, when someone asks for the numbers.
    """
    if exportable and rows_source is None:
        raise ComponentUsageError(
            "ui.datatable: exportable=True needs rows= to be a callable. "
            "The CSV must hold every matching row, so the server has to "
            "re-run your query outside the render that produced the page "
            "— and a plain list is gone by then. Pass a module-level "
            "function instead; apply_query keeps the sort, search, "
            "filters and paging a list had:\n"
            "    from bretzel.components import Query, apply_query\n"
            "    def load_rows(q: Query) -> tuple[list, int]:\n"
            "        return apply_query(my_rows(), COLUMNS, q)\n"
            "    ui.datatable(rows=load_rows, exportable=True, ...)\n"
            "What the page knows (a month, an id) rides a partial: "
            "rows=functools.partial(load_rows, month), with "
            "load_rows(month, q)."
        )
    return exportable


def _value_with_count(counts: Counter[str], count_class: str,
                      value: Any, label: Any) -> Node:
    """A filter option's body : the value, then how many rows carry it.

    A fragment, so the two halves are items of the option's own flex row.
    """
    return FragmentNode(children=(
        TextNode(str(label)),
        Element(tag="span", attrs={"class": count_class},
                children=(TextNode(str(counts.get(str(value), 0))),)),
    ))


def _check_domain(col: Column, domain: list[str]) -> list[str]:
    """Refuse a filter tick-list too large to be one.

    See ``_MAX_FILTER_VALUES`` for why. The message names
    the column and the count, because the usual cause is ``filter=True``
    landing on a free-text field where every row is its own value — and
    from the call site that mistake is invisible.
    """
    if len(domain) > _MAX_FILTER_VALUES:
        raise ComponentUsageError(
            f"ui.datatable: column {col.key!r} has {len(domain)} distinct "
            f"values to tick — over the {_MAX_FILTER_VALUES} a checklist "
            "can usefully hold, and every checkbox carries the whole list "
            "in its action payload, so the page grows with the SQUARE of "
            "it. This is what filter=True does on a free-text column. "
            "Filter on a categorical field, or narrow the domain "
            f'explicitly: ui.column("{col.key}", filter=["a", "b"]).'
        )
    return domain


def _check_state(state: Any) -> type[DatatableState]:
    """Validate the ``state=`` argument, with the fix in the message.

    Two mistakes are worth catching by hand rather than letting them
    surface as an ``AttributeError`` three frames deep : passing an
    *instance* (``state=Issues()``) and passing ``DatatableState``
    itself. The second one is the dangerous one — it renders fine, and
    then two tables on the page silently share one query.
    """
    if isinstance(state, DatatableState):
        raise ComponentUsageError(
            "ui.datatable: state= takes the state CLASS, not an instance — "
            f"state={type(state).__name__} instead of "
            f"state={type(state).__name__}()."
        )
    if not (isinstance(state, type) and issubclass(state, DatatableState)):
        raise ComponentUsageError(
            "ui.datatable: state= must be a DatatableState subclass. "
            "Declare one per table: "
            "`class Issues(DatatableState): pass`."
        )
    if state is DatatableState:
        raise ComponentUsageError(
            "ui.datatable: state= must be a SUBCLASS of DatatableState, not "
            "DatatableState itself — states are keyed by class, so every "
            "table sharing the base would share one sort and one page. "
            "Declare `class Issues(DatatableState): pass` per table."
        )
    return state


def _result_label(total: int, source: int | None) -> str:
    """The footer's count — mentions the narrowing only when it narrowed.

    ``source`` is ``None`` in the callable tier : the component holds no
    rows there, so it does not know how many exist unfiltered and must
    not invent a number. Reading "34 results of 0" is worse than reading
    "34 results", and that is exactly what deriving it from an empty
    local list produced.
    """
    if source is not None and total != source:
        return plural("datatable.results_narrowed", total, total=source)
    return plural("datatable.results", total)
