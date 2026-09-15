"""``Table`` — simple data table with custom cell renderers.

Usage ::

    columns = [
        ui.column("title",    label="Title"),
        ui.column("status",   label="Status",
                  render=lambda v, row: ui.badge(v, color="success")),
        ui.column("assignee", label="Assignee", align="center",
                  render=lambda v, row: ui.avatar(initials=v)),
        ui.column("",         label="",
                  render=lambda v, row: build_actions_dropdown(row)),
    ]

    ui.table(columns=columns, rows=issues)

Each ``rows`` entry is either a dict (looked up by ``column.key``)
or an object whose attributes match the column keys.

The ``render`` callback receives ``(cell_value, row)`` and returns
anything :class:`Component.adopt_slot` can normalise — a Component
instance, a Node, or a plain string. Use it to drop badges, avatars,
buttons, links, dropdowns into cells without escaping HTML.

**Clickable rows.** Pass ``on_item_click=handler`` (a module-level
function) and the table wires every body row as a server action : the
handler receives the row's *key* (``row_key`` column, or the row's
``id``/``pk`` by default). Clicks that land on an interactive child
(a button, link, the actions dropdown, a form control…) do NOT fire the
row click — only the "empty" parts of the row do. Rows become keyboard
operable (``role="button"`` + ``tabindex`` + Enter/Space).

**Empty state.** When ``rows`` is empty the table renders a
:class:`~bretzel.components.feedback.empty_state.EmptyState` automatically
(``empty_text`` / ``empty_icon`` / ``empty_description``, or a full
``empty=callable`` escape hatch) — no hand-rolled placeholder.

**Identity & refresh.** Rows iterate through :func:`ui.each`, so each
row (and the components inside its cells — badges, dropdowns) gets a
stable key derived from ``row_key`` / ``id``. A ``@refreshable`` table
that re-sorts or paginates therefore reconciles cleanly under idiomorph
instead of tearing rows down.

For sort / filter / pagination, compose with the navigation tier
(``ui.pagination``, with the SAME ``color=``) and per-column header
buttons that call server handlers. The simple Table doesn't bake those
in — it stays a display primitive ; the heavier ``Datatable`` is the
place for inline behaviour.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    coerce_children,
    reactive_prop,
)
from bretzel.components.base._wiring import activate_keydown
from bretzel.components.base.events import item_action_attrs
from bretzel.components.data.table.theme import TABLE_THEME
from bretzel.components.feedback.empty_state import EmptyState
from bretzel.components.meta.iteration.each import each
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render.context import current_context
from bretzel.render.iteration import (
    current_iteration_key,
    key_segment,
)

# A row click is suppressed when it lands on an interactive descendant —
# the actions dropdown, a link, a button, a form control. HTMX evaluates
# this filter against the triggering ``event`` (``hx-trigger="click[…]"``)
# so only "blank" parts of the row drive the row action.
#
# ⚠️ The filter must contain NO commas (HTMX splits ``hx-trigger`` on
# commas into separate triggers) and NO ``]`` (HTMX matches the filter's
# closing bracket greedily). So instead of one ``closest('a,button,…')``
# we AND together single-tag ``closest()`` calls — same effect, parser-safe.
_ROW_INTERACTIVE_TAGS = (
    "button", "a", "input", "select", "textarea", "label",
)
_ROW_CLICK_GUARD = " && ".join(
    f"!event.target.closest('{tag}')" for tag in _ROW_INTERACTIVE_TAGS
)

# Keyboard activation for a focusable clickable row : Enter / Space fire
# a synthetic click (caught by the row's own ``hx-trigger="click[…]"``).
# Le garde de cible + les trois noms de touche vivent dans
# ``_wiring.activate_keydown`` — Table était le seul des trois sites à
# porter la garde, et le seul à ignorer le legacy ``Spacebar``.
_ROW_CLICK_KEYDOWN = activate_keydown("$el.click();")


# ───────────────────────────────────────────────────────────────────────────
# Column descriptor
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Column:
    """Describes one column of a :class:`Table` or :class:`Datatable`.

    - ``key`` is the lookup name on each row : ``row[key]`` for dict
      rows, ``getattr(row, key)`` for object rows.
    - ``label`` is the header text. Empty string to skip the header
      label (useful for action columns).
    - ``align`` picks ``left`` / ``center`` / ``right`` — applied to
      both the header and the cells of this column.
    - ``width`` is an arbitrary CSS width (``"8rem"``, ``"10%"``,
      ``"120px"``) set inline on the matching ``<col>``. With the default
      automatic table layout, content can make the column wider; this is
      a preferred width, not a maximum.
    - ``render`` is an optional callback ``(value, row) -> Any`` that
      returns a Component / Node / string to render in the cell. When
      omitted the raw value is shown via ``str()``.
    - ``sortable`` turns the header into a sort control.
    - ``filter`` adds a per-value narrowing popover : ``True`` derives
      the tick-list from the rows (list tier only — with a ``rows=``
      callable the component holds none and says so), a sequence states
      it explicitly.

    **Only :class:`Datatable` honours either** — a plain :class:`Table`
    has nowhere to put the controls and rejects the column outright
    rather than dropping the flags silently.

    One descriptor serves both tables on purpose : moving a display
    table to a Datatable is adding ``sortable=True`` or ``filter=``, not
    rewriting the column list. Both flags are Datatable-only and both are
    rejected here — cf. ``_reject_datatable_columns``.
    """

    key: str
    label: str = ""
    align: str = "left"
    width: str | None = None
    render: Callable[[Any, Any], Any] | None = field(default=None)
    sortable: bool = False
    filter: bool | tuple[str, ...] = False


# Convenience factory exposed as ``ui.column(...)`` so user code
# doesn't need a separate import.
def column(
    key: str,
    *,
    label: str = "",
    align: str = "left",
    width: str | None = None,
    render: Callable[[Any, Any], Any] | None = None,
    sortable: bool = False,
    filter: bool | Sequence[str] = False,
) -> Column:
    """Build a :class:`Column` — sugar so users can do ``ui.column(...)``
    instead of importing the dataclass."""
    return Column(
        key=key, label=label, align=align, width=width, render=render,
        sortable=sortable,
        # Frozen + slots : the domain has to be hashable like the rest.
        filter=tuple(filter) if isinstance(filter, (list, tuple)) else filter,
    )


def read_cell(row: Any, key: str) -> Any:
    """Look up ``key`` on ``row`` — the one row-access rule.

    ``row`` can be a dict, a dataclass-like object, or anything with
    attribute access. Dict lookup wins when both a key and an attribute
    exist. An empty ``key`` (action columns) reads as ``None``.

    Module-level rather than a Table method because Datatable's query
    pipeline sorts and searches the same rows before Table ever sees
    them — two readers, one rule.
    """
    if not key:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


# ───────────────────────────────────────────────────────────────────────────
# Table component
# ───────────────────────────────────────────────────────────────────────────


class Table(Component):
    """Simple data table — header row + body rows, styled by theme."""

    THEME: ClassVar[dict[str, Any]] = TABLE_THEME
    THEME_KEY: ClassVar[str] = "table"
    #: L'event est DÉCLARÉ, et ce n'est pas de la métadonnée.
    #:
    #: Tant qu'il ne l'était pas, `on_item_click=` n'acceptait qu'un callable :
    #: la forme « chaîne d'expression cliente », que tout `on_*` du
    #: framework accepte, y levait un `TypeError` remonté nu de
    #: `functools.partial`, sans nommer le composant ni la prop. Mesuré
    #: le 2026-09-06 sur trois composants livrés
    #: (`.claude/work/audit-declaration-2026-09-06.md`).
    #:
    #: Le routage reste MANUEL — le socle pose l'`hx-post` d'un event
    #: déclaré sur la RACINE, or ici c'est chaque LIGNE qui porte le sien,
    #: avec sa donnée. D'où `item_action_attrs`, le routeur partagé des
    #: quatre composants dans ce cas.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click",)
    #: Le composant possède la boucle : il reçoit ``rows`` puis les
    #: parcourt lui-même, et ``Datatable`` y ajoute recherche, tri et
    #: pagination. L'auteur n'a donc AUCUN endroit où écrire son
    #: balisage — d'où ``ui.column(render=)``, seul point d'entrée
    #: possible. Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "component"
    # The TRUE root is the scroll-container ``<div>`` (a ``<table>`` can't
    # scroll its own overflow) ; the ``<table>`` is a structural inner
    # element. ``DEFAULT_TAG`` names the root, matching the wrapper-div
    # component family (select / file_upload).
    IS_CONTAINER: ClassVar[bool] = False
    # Pure display — all axes are design-time. Row data changes via
    # the rows kwarg (rebuilt on server refresh, not via bindings).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    # Cell density on the standard scale — use ``size="sm"`` for compact.
    size: str = reactive_prop(default="md", emit_attr=False)
    # Accent colour : tints the header (``bg-<color>/5``) and is the
    # value to echo onto a composed ``ui.pagination(color=…)`` so the
    # whole block reads as one. Defaults to ``primary``.
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        *,
        columns: Iterable[Column] = (),
        rows: Iterable[Any] = (),
        row_key: str | Callable[[Any], Any] | None = None,
        on_item_click: Callable[..., Any] | None = None,
        size: str | None = None,
        color: str | None = None,
        empty_text: str = "No data.",
        empty_icon: str | None = "inbox",
        empty_description: str | None = None,
        empty: Callable[[], Any] | None = None,
        head_render: Callable[[Column], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(size=size, color=color, **kwargs)
        self._columns = list(columns)
        self._head_render = head_render
        self._reject_datatable_columns()
        self._rows = list(rows)
        self._row_key = row_key
        self._item_click = on_item_click
        self._empty_text = empty_text
        self._empty_icon = empty_icon
        self._empty_description = empty_description
        self._empty = empty

    def _reject_datatable_columns(self) -> None:
        """Fail fast when a Datatable-only column reaches a plain Table.

        ``ui.column(sortable=True)`` describes a control a display table
        has nowhere to put. Ignoring the flag would be the worse
        outcome : the page renders, the header looks normal, and the
        reader clicks it forever. One descriptor for both tables is only
        safe if the mismatch is loud.

        Unconditional on purpose. Keying it on ``head_render is None`` read
        as "is my caller a Datatable" — but ``head_render`` is a PUBLIC
        parameter, so the guard's off-switch would have been user-reachable
        and ``ui.table(columns=[…sortable…], head_render=mine)`` would
        render exactly the dead header this exists to prevent. Datatable
        consumes ``sortable`` itself and hands Table a normalised column
        list, so the invariant here is simply : a Table never sees it.
        """
        if any(c.sortable or c.filter for c in self._columns):
            offenders = [c.key or "<action column>"
                         for c in self._columns if c.sortable or c.filter]
            raise ComponentUsageError(
                f"ui.table: column(s) {', '.join(offenders)} declare "
                "sortable= or filter=, but a plain table has nowhere to put "
                "either control — the flag would be silently ignored. Use "
                "ui.datatable(state=..., columns=...), or drop the flag."
            )

    # ── Row-click action wiring ─────────────────────────────────────────

    def _row_action_attrs(self, row: Any, index: int) -> dict[str, Any]:
        """Register this row's server action (shared handler id, per-row
        bound key) and return its ready HTMX attribute set + a11y attrs.

        Registered lazily during render — a table that's built but never
        rendered (discarded by conditional rendering / pagination) does no
        action work, and the result rides straight onto the ``<tr>`` with
        no positional bookkeeping.
        """
        raw_key = self._row_identity(row, index)
        # Les trois formes d'un `on_*`, par le routeur partagé. Ce site
        # n'acceptait qu'un callable : une chaîne d'expression cliente y
        # levait un `TypeError` remonté nu de `functools.partial`.
        attrs = item_action_attrs(
            self._item_click,
            event="item_click",
            bind=lambda fn: functools.partial(fn, raw_key),
            owner_id=self.id,
            ctx=current_context(),
            # L'event DÉCLARÉ est `item_click`, celui du DOM est `click` :
            # sans le dire, la part cliente écouterait un event que rien
            # ne dispatche.
            dom_event="click",
            guard=_ROW_CLICK_GUARD,
            # `debounce=` / `throttle=` : le socle ne les
            # applique qu'à l'action de la RACINE.
            modifier=self._trigger_modifier,
        )
        attrs["role"] = "button"
        attrs["tabindex"] = "0"
        attrs["bz-on:keydown"] = _ROW_CLICK_KEYDOWN
        return attrs

    def _has_natural_key(self) -> bool:
        """Whether a stable per-row key exists — an explicit ``row_key`` or
        an ``id`` / ``pk`` on the rows. Gates the ``each`` keyed iteration
        so keyless display tables don't trip its positional-fallback
        warning."""
        if self._row_key is not None:
            return True
        if not self._rows:
            return False
        first = self._rows[0]
        if isinstance(first, dict):
            return "id" in first
        return hasattr(first, "id") or hasattr(first, "pk")

    def _row_identity(self, row: Any, index: int) -> Any:
        """The raw (un-stringified) key bound into a row's click action.

        Honours ``row_key`` (callable or column name), else the ``id`` /
        ``pk`` convention, else the positional index as a last resort.
        """
        rk = self._row_key
        if callable(rk):
            return rk(row)
        if rk is not None:
            return read_cell(row, rk)
        if isinstance(row, dict):
            return row.get("id", index)
        return getattr(row, "id", getattr(row, "pk", index))

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        modifiers = theme.get("modifiers", {})
        aligns = theme.get("aligns", {})
        sizes = theme.get("sizes", {})

        size = self._reactive_values.get("size") or "md"
        size_pad = sizes.get(size, "")
        clickable = self._item_click is not None
        ncols = max(1, len(self._columns))

        # ── Colgroup — drives per-column ``width`` via <col> tags ──
        col_nodes: list[Node] = []
        for col in self._columns:
            col_attrs: dict[str, Any] = {}
            if col.width:
                col_attrs["style"] = f"width: {col.width}"
            col_nodes.append(
                Element(tag="col", attrs=col_attrs, children=())
            )
        colgroup = (
            Element(tag="colgroup", attrs={}, children=tuple(col_nodes))
            if col_nodes
            else None
        )

        # Per-alignment cell classes, composed ONCE (the base slot + the
        # per-size padding + the align utility depend only on ``col.align``)
        # instead of re-joining the same strings for every cell of every
        # row. The empty cell is composed separately (no size padding) so
        # the density scale can't crush its ``p-0``.
        def _slot_classes(slot_key: str) -> dict[str, str]:
            base = slots.get(slot_key, "")
            return {
                a: " ".join(
                    p for p in (base, size_pad, aligns.get(a, "")) if p
                )
                for a in {c.align for c in self._columns}
            }

        head_cls = _slot_classes("head_cell")
        body_cls = _slot_classes("cell")

        # ── Head row ────────────────────────────────────────────────
        head_cells: list[Node] = []
        for col in self._columns:
            # ``head_render`` (Datatable's sort controls) replaces the
            # label entirely — it owns the label too, since the control
            # has to be clickable *and* readable. Normalised through the
            # same coercion as body cells so it accepts a Component, a
            # Node or a plain string.
            if self._head_render is not None:
                children = coerce_children(self._head_render(col))
            else:
                children = (TextNode(col.label),) if col.label else ()
            head_cells.append(
                Element(
                    tag="th",
                    attrs={"class": head_cls[col.align], "scope": "col"},
                    children=children,
                )
            )
        # Teinte d'en-tête : le palier de fond. Le ``<thead>`` descend
        # de la racine, donc il hérite du pont que le socle y a posé —
        # rien à redire ici. (C'était ``bg-<color>/5`` ; le palier vaut
        # 10 %, cf. le collapse voulu de la phase 3.)
        head_class = " ".join(
            p for p in (slots.get("head", ""), "bg-(--bz-bg)") if p
        )
        thead = Element(
            tag="thead",
            attrs={"class": head_class},
            children=(
                Element(tag="tr", attrs={}, children=tuple(head_cells)),
            ),
        )

        # ── Body rows ───────────────────────────────────────────────
        if not self._rows:
            body_rows: list[Node] = [self._empty_row(ncols, slots)]
        else:
            body_rows = []
            # ``each`` pushes a stable per-row key so cell components
            # (badges, dropdowns) keep identity across idiomorph reorders
            # on refresh. Only engaged when a key exists (``row_key`` /
            # ``id`` / ``pk``) — else ``each`` would warn about positional
            # fallback for every keyless display table. Keyless tables
            # iterate plainly.
            row_iter = (
                each(self._rows, key=self._row_key)
                if self._has_natural_key()
                else self._rows
            )
            # ...et la table pousse SA propre identité au-dessus de celle
            # des lignes. Sans ce segment, un composant né dans un
            # ``render=`` de cellule n'a AUCUN parent sur la pile (il est
            # construit pendant le rendu, hors de tout ``with``), donc son
            # id vaut ``root_<kind>_<clé de ligne>`` — et deux tables
            # montrant les mêmes lignes répètent exactement la même suite.
            # Mesuré sur ``/datatable`` du playground : NEUF éléments
            # portaient ``root_dropdown_100``, un par tableau affichant la
            # ligne d'id 100.
            #
            # ``bz-id`` est la clé de DEUX mécanismes — celle par laquelle
            # idiomorph apparie les nœuds après un swap, et celle par
            # laquelle ``scope.absorb`` retrouve un scope client. Neuf
            # candidats pour une cible, c'est un menu qui s'ouvre à la
            # place d'un autre et un sous-arbre remplacé au lieu d'être
            # fusionné. Gardé par ``test_no_duplicate_bz_id.py``.
            with key_segment(self.id):
                for index, row in enumerate(row_iter):
                    cells: list[Node] = []
                    for col in self._columns:
                        cell_value = self._resolve_cell(row, col)
                        cell_children = self._render_cell(
                            cell_value, row, col
                        )
                        cells.append(
                            Element(
                                tag="td",
                                attrs={"class": body_cls[col.align]},
                                children=cell_children,
                            )
                        )
                    row_attrs: dict[str, Any] = {
                        "class": slots.get("row", "")
                    }
                    rkey = current_iteration_key()
                    if self.id and rkey is not None:
                        row_attrs["id"] = f"{self.id}__row_{rkey}"
                    if clickable:
                        row_attrs.update(self._row_action_attrs(row, index))
                    body_rows.append(
                        Element(tag="tr", attrs=row_attrs,
                                children=tuple(cells))
                    )

        tbody = Element(
            tag="tbody",
            attrs={"class": slots.get("body", "")},
            children=tuple(body_rows),
        )

        # ── Table element ───────────────────────────────────────────
        # Striped + hover are baked into the ``table`` slot (the one
        # opinionated look) ; only the clickable affordance is conditional.
        # The table is structural — the id / classes / attrs live on the
        # scroll-container root below, not here.
        table_class_parts = [slots.get("table", "")]
        if clickable:
            table_class_parts.append(modifiers.get("clickable", ""))

        table_children: list[Node] = []
        if colgroup is not None:
            table_children.append(colgroup)
        table_children.append(thead)
        table_children.append(tbody)

        # The ``<table>`` is structural, never user-retagged — hardcoded,
        # not ``self._tag`` (which now names the root wrapper).
        table_el = Element(
            tag="table",
            attrs={"class": " ".join(p for p in table_class_parts if p)},
            children=tuple(table_children),
        )

        # ── Scroll-container root ────────────────────────────────────
        # A ``<table>`` can't scroll its own overflow, so the wrapper owns
        # the horizontal scroll (``overflow-x-auto`` in ``root``) — that's
        # what makes a wide table responsive. It is the true root :
        # ``emit_attrs`` lands here and the render-wrap merges user
        # ``classes=`` / ``style=`` post-render, so compose the root from
        # the slot ONLY (a manual append would double the user classes).
        attrs = self.emit_attrs()
        attrs["class"] = slots.get("root", "")

        return Element(tag=self._tag, attrs=attrs, children=(table_el,))

    # ── Helpers ────────────────────────────────────────────────────────

    def _empty_row(self, ncols: int, slots: dict[str, Any]) -> Element:
        """A single full-width row hosting the empty-state placeholder."""
        return Element(
            tag="tr",
            attrs={},
            children=(
                Element(
                    tag="td",
                    attrs={
                        "class": slots.get("empty_cell", ""),
                        "colspan": str(ncols),
                    },
                    children=self._build_empty(),
                ),
            ),
        )

    def _build_empty(self) -> tuple[Node, ...]:
        """Render the empty-state content : the ``empty=`` escape hatch
        when given, else an auto :class:`EmptyState` from the
        ``empty_text`` / ``empty_icon`` / ``empty_description`` props.

        Les deux branches passent par ``coerce_children`` — c'est la MÊME
        normalisation que celle des cellules, et elle était recopiée ici.
        Deux effets, mesurés le 2026-08-18 :

        - un ``empty=`` qui rend ``None`` donnait la chaîne ``"None"``
          dans la cellule (la copie tombait dans son ``str(result)``) ;
          il donne maintenant une cellule vide ;
        - le détachement avait deux propriétaires, donc la gate
          ``test_render_hatch_universal`` restait verte sur ``empty=``
          quand on débranchait celui du socle."""
        if self._empty is not None:
            return coerce_children(self._empty())
        return coerce_children(
            EmptyState(
                self._empty_text,
                icon=self._empty_icon,
                description=self._empty_description,
            )
        )

    @staticmethod
    def _resolve_cell(row: Any, col: Column) -> Any:
        """Look up the cell's raw value on the row — cf. :func:`read_cell`."""
        return read_cell(row, col.key)

    @staticmethod
    def _render_cell(
        value: Any, row: Any, col: Column
    ) -> tuple[Node, ...]:
        """Turn a cell value into a tuple of Node children.

        The default (no ``col.render`` callback) stringifies the raw
        value ; the callback's return shape is normalised by
        :func:`~bretzel.components.base.coerce_children`.
        """
        return coerce_children(col.render(value, row) if col.render else value)
