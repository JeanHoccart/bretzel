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

    @refreshable(deps=[Issues, IssueStore])
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

**It must sit inside a ``@refreshable``** whose ``deps`` include the state
class. No component owns a refresh zone in Bretzel — clicking a header
mutates the state, and it is the enclosing zone's ``deps=`` that turns
that mutation into a re-render. Two lines, and no new framework
mechanism.

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
import unicodedata
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
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import plural, state_qualname, text
from bretzel.render.context import current_context
from bretzel.render.iteration import key_segment
from bretzel.state import form_value
from bretzel.state.datatable import DatatableState, Query

# Form field names for the two controls whose value rides back with the
# action, assembled by :func:`_field`.
# A tick-list past this many values stops being a filter and becomes a
# scrolling wall. That is the whole reason now : the quadratic payload
# that first motivated the cap (every checkbox carrying the whole domain
# in its own signed action — 40 values → 29 KB, 200 → 800 KB, 70% of the
# response) died when the ticks went client-side and the domain started
# riding ONCE on the close action. The wall did not. ``filter=True`` on a
# free-text column (a name, a title) hits it instantly, one distinct
# value per row. Refused rather than shipped, per the same argument as
# the export guard.
_MAX_FILTER_VALUES = 50

#: Le nom de champ du carrier de filtre — suffixé par la clé de colonne.
#: Porté par l'input caché du combobox, lu par :func:`apply_filter`.
_FILTER_FIELD = "bz_dt_filter"

#: L'invite du champ de recherche DANS un panneau de filtre. Distincte de
#: ``search_placeholder=``, qui décrit la recherche globale : passer
#: « Search issues… » à la table le recopiait dans chaque panneau, où il
#: nomme la mauvaise liste — on y cherche des VALEURS de colonne, pas des
#: lignes.

_PAGE_FIELD = "bz_dt_page"
_SEARCH_FIELD = "bz_dt_search"

#: The one download endpoint, served by ``server/routing/datatable.py``.
EXPORT_ROUTE = "/_bretzel/datatable.csv"


def _rows_ref(rows_source: Any) -> str:
    """Address the rows callable the same way a handler is addressed."""
    from bretzel.components.base.events import encode_handler_id

    return encode_handler_id(rows_source)


def _encode_export(query: Query, rows_ref: str, columns: list,
                   filename: str) -> str:
    """Pack what the download endpoint needs into one signed parameter.

    **The QUERY travels, not the state reference.** An export link is a
    plain browser navigation : no ``X-Bretzel-Page-ID`` header, so the
    server cannot resolve the reader's page-scoped state and would read
    a pristine one — exporting the default view while the screen shows a
    filtered one. Measured, not feared : that is exactly what the first
    version did, and the export test caught it.

    Baking the query in is also free, because the link is re-rendered by
    the same zone refresh that changed the query. It cannot go stale.

    The rest is what the endpoint cannot rediscover : the callable to
    re-run, and the ``(key, label)`` pairs, since there is no component
    left to ask. Signed, so a hand-edited ``rows_ref`` cannot point the
    endpoint at an arbitrary function.
    """
    blob = json.dumps({"q": dataclasses.asdict(query), "r": rows_ref,
                       "c": columns, "f": filename},
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
    "imports différés" escape hatch is for. Reused rather than
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
    long after the action was signed. ``domain`` DOES ride in the bound
    args : ``set_filter`` needs it to tell "everything ticked" (no
    filter) from a partial selection, and the server cannot re-derive it
    in the callable tier, where it holds no rows.
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


def _fold(text: str) -> str:
    """Case- and accent-insensitive form of ``text``, for comparison only.

    NFKD splits an accented letter into base + combining mark ; dropping
    the marks leaves the base. Never shown to anyone — the rendered cell
    keeps its accents.
    """
    folded = text.casefold()
    if folded.isascii():
        # NFKD is the identity on ASCII and ASCII carries no combining
        # marks, so the branch cannot change a result — it only skips the
        # walk. Checked AFTER casefold on purpose : ``ẞ`` folds INTO
        # ASCII ("ss") and takes the fast path correctly. Measured on a
        # sorted 10k-row ASCII column : 52 ms -> 17 ms.
        return folded
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


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


def column_domain(rows: Sequence[Any], key: str) -> list[str]:
    """Every distinct value column ``key`` takes across ``rows``, sorted.

    The tick-list a filter popover offers. Derived from the FULL source,
    never from the current page or the current filter — a value you just
    unticked has to stay in the list, or you could not tick it back.
    """
    if rows and isinstance(rows[0], dict):
        # Dict branch hoisted out of the comprehension : ``read_cell``'s
        # isinstance + call per cell was ~50% of this pass, and this walks
        # EVERY row of the source, per filterable column, on every render.
        seen = {str(row.get(key)) for row in rows}
    else:
        seen = {str(read_cell(row, key)) for row in rows}
    # Folded sort, so the tick-list doesn't dump every accented value
    # after Z — the same complaint the row sort exists to answer.
    return sorted((v for v in seen if v not in ("", "None")), key=_fold)


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
    # and slice each build a new list), so the defensive copy was a full
    # extra pass over the source on every render — measured at 88% of
    # this function's cost in the common no-search-no-sort path.
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
    # dependency tracking (~590 ns inside a render, vs 16 ns for a
    # local). Read per row per pass it cost 2N+1 tracked reads, and the
    # first one already registers the dependency, so the rest were pure
    # overhead. Measured at 10k rows : 23.0 ms -> 5.6 ms.
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
    #: Comme ``Table``, en plus marqué : le pipeline de requête cherche,
    #: filtre, trie et pagine avant que quoi que ce soit ne soit rendu.
    #: Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    IS_CONTAINER: ClassVar[bool] = False
    #: ``item_click`` est DÉCLARÉ, même si ce composant ne le câble pas
    #: lui-même : il passe ``on_item_click=`` à la ``Table`` qu'il rend,
    #: qui le route par ``item_action_attrs``. Les trois formes d'un
    #: ``on_*`` marchent donc ici comme là — un callable serveur, une
    #: chaîne d'expression cliente, ou une liste des deux.
    #:
    #: ⚠️ Il était le dernier des quatre à accepter un clic sans le
    #: déclarer (2026-09-07). Ne PAS déclarer ne rendait rien inerte, ça
    #: rendait la surface introspectée FAUSSE : ``bretzel describe
    #: datatable`` lit ``EVENTS``, et disait « aucun event » d'un
    #: composant qui en accepte un. Le socle, lui, ne voit jamais passer
    #: ce handler — c'est un paramètre nommé de l'``__init__``, pas un
    #: ``**kwargs`` — donc la déclaration ne recâble rien sur la racine.
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
        search_placeholder: str = "Search…",
        exportable: bool = False,
        export_filename: str = "export.csv",
        max_height: str | None = None,
        row_key: str | Callable[[Any], Any] | None = None,
        on_item_click: Callable[..., Any] | None = None,
        size: str | None = None,
        color: str | None = None,
        empty_text: str = "No data.",
        empty_icon: str | None = "inbox",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
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
        return _check_domain(col, column_domain(self._rows, col.key))

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
        declared the state in its ``deps``. Nothing errors, nothing
        logs ; the reader just clicks a header that does nothing.

        So the check runs at construction, while the enclosing zone is
        still on the parent stack, and names both the state and the fix.
        """
        if not self._is_interactive():
            return

        from bretzel.render import maybe_current_context, zone_ids_watching

        ctx = maybe_current_context()
        if ctx is None:  # test rig with no context — nothing to check
            return
        enclosing = {
            getattr(parent, "_refresh_id", None) for parent in ctx.parent_stack
        }
        if enclosing & zone_ids_watching(self._state_cls):
            return

        name = self._state_cls.__name__
        raise ComponentUsageError(
            f"ui.datatable(state={name}) is not inside a @refreshable zone "
            f"that watches {name}. Sorting, paging and searching all work "
            f"by mutating {name} — with no zone declaring it in deps=, the "
            "controls would post and the page would never change. Wrap it :\n"
            f"    @refreshable(deps=[{name}])\n"
            "    def my_table() -> None:\n"
            f"        ui.datatable(state={name}, ...)"
        )

    def _size_map(self) -> dict[str, str]:
        """The composed children's size tokens for this table's ``size``."""
        sizes = self._resolved_theme().get("sizes", {})
        size = self._reactive_values.get("size") or "md"
        return sizes.get(size, sizes.get("md", {}))

    # ── Header ─────────────────────────────────────────────────────────

    def _head_title(self, col: Column) -> Any:
        """Build one header : the sort control, or a plain label.

        Filters used to live here too, behind a ``⋮`` per column, which
        is why this used to sit behind a ``_head_cell`` assembler. They
        moved to the toolbar : a header is for reading the column name
        and ordering by it, and hanging a second control off it made
        every filterable column wider and the free-text one narrower.
        With nothing left to assemble, the assembler is gone and this IS
        the ``head_render=`` seam.
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
            # the plain header beside it, and skipping it is what made one
            # header row read half accent-blue, half muted grey, with the
            # split following nothing the eye can interpret. The accent is
            # spent on the ACTIVE column only, where it means something.
            # ⚠️ Ce n'est PAS la convention « couleur d'un sous-composant
            # embedded » que ce commentaire citait jusqu'au 2026-08-07 :
            # celle-là parle d'un composant subordonné qui hérite de
            # l'encre de son parent, et elle range justement Button parmi
            # les exceptions. La règle appliquée ici est
            # ``components.md`` § « l'accent marque le pair ACTIF ».
            color=(self._reactive_values.get("color") or "primary")
            if active else "current",
            # Constant on purpose, and baselined in
            # ``test_child_component_size_is_not_frozen`` with the reason :
            # the header type scale is Table's and does not move with
            # ``size=``, so a sortable header must not move either or it
            # stops matching the plain header next to it. Cf. theme.py.
            size="xs",
            icon_right=icons.get(state.sort_dir if active else "", ""),
            classes=slots.get("head_button", ""),
            on_click=functools.partial(
                sort_by, state_qualname(self._state_cls), col.key
            ),
            # Read by the probes and by anyone debugging a sort that
            # doesn't stick — the DOM says which column is active.
            attrs={"data-sort": state.sort_dir if active else "none"},
        )

    def _column_filter(self, col: Column, *, colour: str,
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
        """
        state = self._state_cls()
        ref = state_qualname(self._state_cls)
        domain = self._filter_domains.get(col.key, [])
        kept = state.filters.get(col.key)
        narrowed = kept is not None
        picked = list(kept) if narrowed else list(domain)
        # Stable per (table, column) : the combobox scopes its own
        # ``hx-include`` by this id (so the close action carries the
        # picks), and idiomorph keeps matching the same node across
        # refreshes.
        box_id = f"bzf_{self._state_cls.__name__}_{col.key}"

        label = col.label or col.key
        return Combobox(
            domain,
            id=box_id,
            value=picked,
            multiple=True,
            bulk_actions=True,
            name=_field(_FILTER_FIELD, self._state_cls) + f"__{col.key}",
            placeholder=text("datatable.filter_placeholder"),
            color=colour,
            size=sizes.get("toolbar", "sm"),
            trigger=Button(
                f"{label} · {len(picked)}/{len(domain)}" if narrowed else label,
                # ``soft`` DANS LES DEUX ÉTATS, et c'est la COULEUR qui
                # dit lequel.
                #
                # Pas ``ghost`` : sa boîte n'existe que sous
                # ``not-disabled:hover:``, donc au repos c'est du texte, et
                # une barre d'outils est un endroit où l'on doit VOIR ce
                # qui est pressable avant de le presser. C'est la règle
                # que ``theme/tailwind.py`` écrit noir sur blanc au bout
                # de sa note sur ``@custom-variant hover`` : « ``hover:``
                # must still never CARRY an affordance ». Elle vaut
                # partout, pas seulement au doigt — la boîte d'un ghost
                # EST son affordance. (Un ``ui.button(variant="ghost")``
                # reste juste DANS un conteneur qui dessine déjà la
                # boîte : cf. ``_head_title``, où le ``<th>`` la porte.)
                #
                # Et une SEULE variante pour les deux états parce que
                # changer de variante change la boîte : la barre sautait
                # au premier filtre posé. Le ton change, la géométrie
                # non.
                variant="surface",
                # Convention « l'accent marque le pair ACTIF » —
                # cf. ``components.md`` § du même nom.
                color=colour if narrowed else "current",
                size=sizes.get("toolbar", "sm"),
                icon_left="list-filter",
            ),
            on_close=functools.partial(apply_filter, ref, col.key, domain),
        )

    def _export_link(self, *, slots: dict[str, str],
                     sizes: dict[str, str]) -> Node:
        """The CSV button — a real link, not an action.

        A download cannot ride the action pipeline : the response has to
        be the file, and HTMX would try to swap it into the page. So it
        is a plain signed GET that the bridge leaves alone
        (``hx-boost="false"``).
        """
        from bretzel.server.handlers import sign_action

        columns = [[c.key, c.label] for c in self._columns if c.key]
        payload = _encode_export(
            self._state_cls().to_query(for_export=True),
            _rows_ref(self._rows_source), columns, self._export_filename,
        )
        context = current_context()
        key = getattr(getattr(context.app, "config", None), "_action_key", b"")
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
            "Export CSV",
            tag="a",
            classes=slots.get("export", ""),
            variant="surface",
            size=sizes.get("toolbar", "sm"),
            color="current",
            icon_left="download",
            href=f"{EXPORT_ROUTE}?q={payload}"
                 f"&sig={sign_action(key, EXPORT_ROUTE, payload) if key else ''}",
            attrs={
                "hx-boost": "false",
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

    # ── Ce que la barre d'outils AFFICHE, colonne par colonne ─────────
    #
    # C'est ce qui décide de ``_toolbar_blind_to()``, donc de ce qu'on a
    # le droit de préserver :
    #
    # - la recherche rend ``state.search`` ;
    # - le bouton « Clear filters » n'existe que si ``state.filters`` ;
    # - chaque filtre de colonne coche depuis ``state.filters`` ;
    # - l'export — S'IL Y EN A UN — sérialise ``to_query(for_export=True)``,
    #   qui normalise ``page`` à 1 mais garde le tri, la taille de page,
    #   la recherche et les filtres.
    #
    # Rien d'autre. Et sans bouton d'export, la dernière ligne disparaît
    # avec lui : c'est toute la différence entre les deux ensembles.

    #: Les six champs de :class:`DatatableState`. Un champ ajouté par une
    #: sous-classe applicative n'y figure pas, et c'est voulu : la barre
    #: ne peut rien affirmer sur ce qu'elle ne connaît pas, donc un champ
    #: inconnu qui bouge fait rendre la barre.
    _STATE_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"sort_key", "sort_dir", "page", "per_page", "search", "filters"}
    )
    #: Ce que la barre PEINT : la valeur du champ de recherche, et les
    #: étiquettes « N/total » des filtres (plus le bouton « effacer »,
    #: qui n'apparaît que si un filtre est posé).
    _TOOLBAR_READS: ClassVar[frozenset[str]] = frozenset({"search", "filters"})
    #: Ce que l'URL SIGNÉE du bouton CSV embarque en plus. ``page`` n'y
    #: est pas : ``to_query(for_export=True)`` la normalise à 1 — c'est
    #: précisément ce qui rendait la barre préservable au changement de
    #: page (cf. le commentaire dans ``state.py``).
    _EXPORT_READS: ClassVar[frozenset[str]] = frozenset(
        {"sort_key", "sort_dir", "per_page", "search", "filters"}
    )

    def _toolbar_blind_to(self) -> frozenset[str]:
        """Les champs dont un changement laisse la barre à l'octet près.

        C'était une constante — ``{"page"}`` — et elle était juste pour
        une table EXPORTABLE seulement. Sans bouton CSV, la barre ne lit
        ni le tri ni la taille de page : elle repartait entière à chaque
        clic d'en-tête, 12 Ko sur les 28 d'une table de quatre colonnes,
        pour des octets rigoureusement identiques. Et ``exportable``
        vaut ``False`` par défaut, donc c'était le cas courant.

        La forme constante ne pouvait pas dire ça : la réponse dépend de
        ce que CETTE table rend. D'où un ensemble dérivé de ce que la
        barre lit vraiment — et une gate qui mute chaque champ et compare
        les octets, plutôt qu'une liste tenue à jour à la main.
        """
        reads = self._TOOLBAR_READS
        if self._exportable:
            reads = reads | self._EXPORT_READS
        return self._STATE_FIELDS - reads

    def _toolbar_can_be_preserved(self) -> bool:
        """La barre est-elle démontrablement inchangée par cette requête ?

        Elle pèse **44 %** de la zone (35 Ko sur 79, mesuré sur un
        datatable de 5 lignes avec trois filtres) et se re-rendait à
        chaque clic de pagination alors qu'aucun de ses octets ne bouge.

        Trois conditions, toutes nécessaires :

        1. **Rendu partiel.** Sur une page complète la barre n'est pas
           encore dans le DOM : la préserver la ferait disparaître.
        2. **On SAIT ce qui a changé.** ``ctx.changed_fields`` vide veut
           dire « on ne sait pas » (page complète, refetch SSE), pas
           « rien » — donc on rend tout.
        3. **Le changement porte sur cet état-ci, et seulement sur des
           champs auxquels la barre est aveugle** — ``_toolbar_blind_to()``,
           qui est plus large quand la table n'exporte pas. Une autre
           table qui bouge, un état applicatif qui bouge : on ne conclut
           rien et on rend tout.

        Plus un garde de sécurité : une barre préservée garde la
        **signature d'origine** de ses actions, timestamp compris. Sous
        ``action_max_age``, elle finirait par expirer sans jamais être
        rafraîchie — l'utilisateur pagine une heure, clique un filtre, et
        se prend un 403. Le défaut est ``None`` (valide indéfiniment),
        donc ce garde ne coûte rien à personne aujourd'hui ; il évite que
        l'anti-rejeu et cette optimisation se découvrent incompatibles
        des mois plus tard, en production, chez quelqu'un d'autre.
        """
        ctx = current_context()
        if not getattr(ctx, "is_partial", False):
            return False
        config = getattr(getattr(ctx, "app", None), "config", None)
        if getattr(config, "action_max_age", None) is not None:
            return False
        changed = getattr(ctx, "changed_fields", None) or {}
        if not changed:
            return False
        mine = changed.get(self._state_cls)
        if not mine:
            return False
        # Un AUTRE état a bougé dans la même requête : son handler a pu
        # écrire dans le nôtre par un chemin qu'on ne voit pas. On ne
        # spécule pas.
        if set(changed) != {self._state_cls}:
            return False
        return mine <= self._toolbar_blind_to()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        """Tout ce que la table bâtit naît sous l'identité de son ÉTAT.

        Sans ça, le pager, la recherche et les boutons de la barre se
        construisent pendant ``render()`` — donc sans parent sur la pile —
        et reçoivent un id **positionnel et global à la page** :
        ``root_pagination_0`` pour la première table, ``root_pagination_1``
        pour la deuxième. Or une zone se re-rend SEULE : le générateur
        repart de zéro et la deuxième table renvoie ``root_pagination_0``,
        c'est-à-dire l'id de la PREMIÈRE.

        Mesuré le 2026-08-07, deux tables sur une page ::

            avant le clic : ['root_pagination_0', 'root_pagination_1']
            clic page 5 sur B
            après le clic : ['root_pagination_0', 'root_pagination_0']

        Et le symptôme que ça produit est exactement celui rapporté :
        ``bz-id`` étant la clé d'appariement d'idiomorph ET celle de
        ``scope.absorb``, le pager de B adopte le scope de A — donc son
        ``_total`` — et affiche 7 pages au lieu de 5 ; puis l'entrée
        cachée de A voit sa valeur changer et POSTe à son tour. **Un clic,
        deux requêtes**, et la mauvaise table qui navigue.

        La clé est le nom de la classe d'état, pas ``self.id`` : l'id de
        la table est lui aussi positionnel, donc instable entre un rendu
        complet et un rendu de zone. Le nom de l'état, lui, est le même
        des deux côtés — c'est déjà l'identité que ``_field()`` et
        ``bzf_<État>_<colonne>`` utilisent. Deux tables statiques qui
        partagent une classe restent départagées par le compteur de
        frères d'``IdGenerator`` (``…_1``, ``…_2``), ce qui leur rend leur
        ancien comportement positionnel — elles ne se re-rendent jamais
        partiellement, donc c'est correct.
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
        # ``hx-preserve`` : HTMX garde le nœud VIVANT et ignore celui qui
        # arrive. On envoie donc une coquille vide quand la barre ne peut
        # pas avoir changé — et les 35 Ko de filtres ne repartent pas sur
        # le fil à chaque clic de pagination. Vérifié au navigateur : le
        # sous-arbre préservé survit à un morph OOB de zone.
        # ``_has_toolbar`` garde les DEUX branches, et c'est la seule
        # forme correcte : une coquille ``hx-preserve`` n'a de sens que
        # s'il existe un nœud de même ``id`` à préserver. Émise pour une
        # table qui n'a aucun contrôle, elle insérerait une div morte
        # portant l'id de la barre — et le jour où quelqu'un ajoute un
        # filtre à cette table, il ne le verrait jamais apparaître : la
        # barre fraîche serait préservée à l'état vide. Les deux branches
        # doivent donc répondre à la MÊME question, d'où un prédicat
        # partagé plutôt que deux conditions à garder d'accord.
        toolbar_id = f"bzdt_{self._state_cls.__name__}_toolbar"
        if not self._has_toolbar(state):
            pass
        elif self._toolbar_can_be_preserved():
            # La coquille : même ``id``, ``hx-preserve``, aucun enfant.
            # HTMX garde le nœud vivant et jette celui-ci — donc les 35 Ko
            # de filtres ne repartent pas sur le fil.
            #
            # Sortie SÈCHE, plutôt qu'un drapeau ``preserve`` re-testé
            # devant chacun des quatre contrôles (dont un DANS la boucle
            # sur les colonnes) : quatre gardes qui disent toutes la même
            # chose, pour construire une liste qu'on jette ensuite.
            children.append(Element(
                tag="div",
                attrs={"id": toolbar_id, "hx-preserve": "true"},
                children=(),
            ))
        else:
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
        # `debounce=` / `throttle=` posés sur le datatable valent pour le
        # clic de LIGNE, qui est rendu par la Table interne. Le socle les
        # a déjà traduits en modificateur de trigger sur CETTE instance ;
        # les milliseconds brutes, elles, ont été consommées. On transmet
        # donc le modificateur, pas le kwarg — sans quoi le délai est
        # accepté puis perdu, ce qu'a mesuré
        # `test_trigger_modifiers_survive` le 2026-09-07.
        table._trigger_modifier = self._trigger_modifier
        children.append(Component.render_detached(table))

        # ── Footer ──────────────────────────────────────────────────
        info_class = " ".join(
            p for p in (slots.get("footer_info", ""), sizes.get("info", ""))
            if p
        )
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
        """Cette table a-t-elle une barre d'outils, du tout ?

        Le pendant structurel de :meth:`_toolbar_can_be_preserved` — qui
        répond « la barre a-t-elle pu changer ? », une question qui n'a
        de sens que s'il y a une barre. Les quatre termes sont exactement
        ceux que :meth:`_toolbar_node` sait rendre, et c'est pour cette
        raison qu'ils vivent ici plutôt que recopiés à deux endroits :
        les deux doivent répondre pareil ou l'invariant ``coquille ⇔
        nœud vivant`` se rompt.

        ``state.filters`` en fait partie parce que le bouton « Clear
        filters » n'existe QUE quand quelque chose filtre — une table
        sans autre contrôle gagne donc une barre au premier filtre posé.
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
        """La barre d'outils complète.

        Appelée uniquement quand :meth:`_has_toolbar` est vrai et que la
        barre ne peut PAS être préservée — donc elle n'a à reconnaître
        aucun de ces deux cas.
        """
        tools: list[Node] = []
        if self._search:
            tools.append(Component.render_detached(Input(
                value=state.search,
                name=_field(_SEARCH_FIELD, self._state_cls),
                placeholder=self._search_placeholder,
                icon_left="search",
                # Vider la recherche au clavier demande un select-all
                # suivi d'un effacement ; la croix le fait en un geste et
                # repart avec le `change`, donc le serveur laisse tomber
                # la recherche sans qu'on ait rien à recâbler ici.
                clearable=True,
                size=sizes.get("toolbar", "sm"),
                classes=" ".join(p for p in (
                    slots.get("search", ""), sizes.get("search", ""),
                ) if p),
                on_change=functools.partial(search_for, ref),
            )))
        # Only offered once something IS filtered : a permanently visible
        # "Clear filters" is a button that does nothing most of the time.
        if state.filters:
            tools.append(Component.render_detached(IconButton(
                "filter-x",
                # Une ICÔNE, pas « Clear filters » en toutes lettres :
                # ce contrôle n'apparaît QUE lorsque quelque chose filtre,
                # donc il ajoute une largeur pile au moment où la barre
                # est la plus chargée — c'est lui qui poussait l'export à
                # la ligne. L'icône rend ~78 px à la ligne.
                #
                # `error` et pas l'encre ambiante : c'est le seul contrôle
                # de la barre qui DÉFAIT quelque chose, et une icône n'a
                # pas de texte pour le dire à sa place. Même intention que
                # le « Clear » du panneau de filtre, dont le thème vire à
                # l'error (`header_btn_muted`). Pas `primary` : l'accent
                # est réservé au filtre ACTIF (cf. `components.md` §
                # « l'accent marque le pair ACTIF »), et une remise à zéro
                # n'est pas un état à signaler.
                variant="surface", color="error",
                size=sizes.get("toolbar", "sm"),
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
                    self._column_filter(col, colour=color, sizes=sizes)
                ))
        if self._exportable:
            tools.append(self._export_link(slots=slots, sizes=sizes))
        return Element(
            tag="div",
            attrs={
                # ``id`` OUI — c'est la cible que la coquille vise.
                # ``hx-preserve`` NON, et c'est tout le contraire d'un
                # détail : HTMX lit l'attribut sur le nœud QUI ARRIVE
                # et, s'il le trouve, garde l'ANCIEN. Le porter ici
                # ferait ignorer la barre fraîche — le bouton « Clear
                # filters » n'apparaîtrait jamais et le filtre actif
                # ne se colorerait pas. Constaté au navigateur : 27
                # résultats affichés, et aucun bouton pour défaire le
                # filtre qui les avait produits.
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
            "function instead:\n"
            "    def load_rows(q: Query) -> tuple[list, int]:\n"
            "        rows, total = ..., ...\n"
            "        return rows, total\n"
            "    ui.datatable(rows=load_rows, exportable=True, ...)"
        )
    return exportable


def _check_domain(col: Column, domain: list[str]) -> list[str]:
    """Refuse a filter tick-list too large to be one.

    See ``_MAX_FILTER_VALUES`` for the measured cost. The message names
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
