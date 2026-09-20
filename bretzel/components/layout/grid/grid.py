"""``Grid`` — CSS-grid container, sibling of :class:`Flex`.

Use a grid (not a flex) when you want **two-dimensional alignment** :
items lined up both along rows AND columns. Flex aligns along a
single axis ; Grid aligns along both.

API :

- ``cols=int`` — static N columns at every breakpoint.
- ``cols=dict`` — responsive : ``{"base": 1, "sm": 2, "md": 3, "lg": 4}``.
  Keys are Tailwind breakpoint prefixes ; ``"base"`` (or empty / ``"xs"``)
  applies at all sizes and gets no prefix.
- ``cols=str`` — escape hatch : ``"none"`` / ``"auto"`` / any literal
  Tailwind class (``"grid-cols-[200px_1fr]"``) flows through verbatim.
- ``min_col=`` — **the grid counts its columns itself**. Instead of
  declaring how many columns at which screen width, you declare a
  column's MINIMUM width: ``ui.grid(min_col="16rem")``. Exclusive with
  ``cols=``.
- ``gap=`` — same 5-step scale as :class:`Flex` / :class:`VStack`
  (``none / xs / sm / md / lg / xl``), and it takes the SAME responsive
  dict as ``cols`` : ``gap={"base": "sm", "md": "lg"}``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    responsive_classes,
)
from bretzel.components.layout.grid.theme import GRID_THEME
from bretzel.core.tree import Element


def _cols_class(cols: Any) -> str:
    """Translate ONE ``cols`` value into its Tailwind class.

    ``int`` → ``grid-cols-N``. ``str`` → ``"none"`` / ``"auto"`` map to
    ``grid-cols-{value}`` ; anything else flows through verbatim (raw
    Tailwind escape hatch). Breakpoints are NOT handled here —
    :func:`responsive_classes` wraps this and owns the ``{bp}:`` prefixing
    for every graded prop in the library.
    """
    if cols is None or isinstance(cols, bool):
        return ""
    if isinstance(cols, int):
        return f"grid-cols-{cols}"
    if isinstance(cols, str):
        if cols in ("none", "auto"):
            return f"grid-cols-{cols}"
        return cols
    return ""


class Grid(Component):
    """Two-dimensional layout container."""

    THEME: ClassVar[dict[str, Any]] = GRID_THEME
    THEME_KEY: ClassVar[str] = "grid"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # ``cols`` does not go through a table: ``_cols_class`` assembles it
    # as an f-string, and its domain is closed by ``_LAYOUT_CLASSES``.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("gaps",)
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"cols", "gap"})

    cols: Any = reactive_prop(default=None, emit_attr=False)
    #: A column's MINIMUM width. The grid then fits as many as it can
    #: and wraps the rest — ``repeat(auto-fit, minmax(X, 1fr))``, the
    #: canonical CSS idiom, Chakra's ``minChildWidth``.
    #:
    #: Why it exists when ``cols=`` is already responsive: an ``xl:``
    #: prefix reads the WINDOW's width, not the grid's. Under a shell
    #: with a side bar, the two diverge by the bar's width — measured on
    #: the CRM, 4 columns of 244 px where the content only has 1024 px,
    #: so a 256 px ``ui.toggle_group`` outside. ``auto-fit`` reads the
    #: real room.
    min_col: Any = reactive_prop(default=None, emit_attr=False)
    # ``Any``, not ``str`` : both graded props take a breakpoint dict.
    gap: Any = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        cols: int | dict | str | None = None,
        min_col: str | None = None,
        gap: str | dict | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the default) — no more ``if x is not None`` guard to
        # retype.
        super().__init__(cols=cols, min_col=min_col, gap=gap, **kwargs)
        # Both decide the number of columns. Accepting them together
        # would let the sheet's order decide — so a result that reads in
        # neither of the two calls. Refused at CONSTRUCTION, where the
        # stack still carries the caller's line.
        if cols is not None and min_col is not None:
            raise ComponentUsageError(
                "ui.grid(cols=…, min_col=…): both decide the number of "
                "columns, and both set `grid-template-columns` — the "
                "winner would depend on the Tailwind sheet's order, not "
                "on yours.\n"
                "  cols=      you declare how many columns, per WINDOW "
                "step;\n"
                "  min_col=   you declare a column's minimum width, and "
                "the grid counts by itself, on its REAL room."
            )
        # Validated HERE and not at render: a raise from ``render``
        # gives a stack with no frame of the caller, so it names the
        # accepted values without saying which of the page's N
        # ``ui.grid`` is at fault. Same trade-off as ``Flex.grow``.
        if min_col is not None:
            self._min_col_class(min_col, self._min_col_table())

    def _min_col_table(self) -> dict[str, str]:
        """This component's ``min_cols`` table, user override included.
        One method and not two reads: ``__init__`` validates and
        ``render`` resolves, and the two must look at the SAME table —
        otherwise a ``Theme(components=…)`` would make validation pass
        and render something else."""
        return self._resolved_theme().get("min_cols", {})

    @staticmethod
    def _min_col_class(min_col: Any, table: dict[str, str]) -> str:
        """``min_col=``'s class, or a raise that NAMES the values.

        A width outside the table would render the empty string: the grid
        would fall back on a single column, with no error and saying
        nothing.
        """
        entry = table.get(min_col)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"min_col={min_col!r} is not a known width. Accepted "
                f"values: {accepted}. The table is closed so that every "
                f"class is WHOLE, hence visible to the production Tailwind "
                f"compiler; for another width, write it at the call site "
                f"with cols='grid-cols-[…]'."
            )
        return entry

    def render(self) -> Element:
        theme = self._resolved_theme()
        cols = self._reactive_values.get("cols")
        gap = self._reactive_values.get("gap") or "md"

        parts: list[str] = []
        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)
        min_col = self._reactive_values.get("min_col")
        if min_col:
            # Can no longer raise: ``__init__`` has already refused the
            # unknown.
            parts.append(self._min_col_class(min_col, self._min_col_table()))
        else:
            cols_cls = responsive_classes(cols, _cols_class)
            if cols_cls:
                parts.append(cols_cls)
        gaps = theme.get("gaps", {})
        gap_cls = responsive_classes(gap, lambda v: gaps.get(v, ""))
        if gap_cls:
            parts.append(gap_cls)
        # User classes set by the ``_apply_universal_modifiers`` wrap —
        # do not re-append here (duplicate). Guarded by
        # test_no_manual_user_class_append.py.

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(p for p in parts if p).strip()

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )
