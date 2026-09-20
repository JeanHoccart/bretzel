"""Default :class:`Datatable` theme.

The Datatable owns almost no visual identity of its own : the table is a
composed :class:`~bretzel.components.data.table.Table`, the search box a
composed ``ui.input``, the pager a composed ``ui.pagination``, the sort
control a composed ``ui.button``. Each of those already carries its own
look, and re-styling them here would fork the design system.

What is left for this theme is the **chrome around them** — the toolbar
strip, the footer strip, and the scroll frame — plus the two things the
composed pieces cannot express on their own : the sticky header and the
sort-direction affordance on the active column.

Slots :
- ``root``        : the vertical stack (toolbar / table / footer)
- ``toolbar``     : the strip above the table (search box, filter triggers)
- ``search``      : width constraint on the composed search input
- ``export``      : pushes the CSV control to the far end of the toolbar
- ``footer``      : the strip below the table (result count + pager)
- ``footer_info`` : the "N results" text
- ``head_button`` : layout override for the composed sort button, so a
  ``ui.button`` sits in a ``<th>`` like a header label rather than like a
  button (full width, inherited type scale, no padding of its own)
- ``head_static`` : the same metrics for a NON-sortable header, so the two
  kinds of column align on the same baseline

The per-column filter has NO slot here : it is a ``ui.combobox``
(``multiple``, ``bulk_actions``, custom ``trigger=``), so its panel, its
tick-list, its search field and its header bar are the combobox's own
theme. Everything that used to live here — ``filter_panel``,
``filter_option``, ``filter_rule``, ``filter_search``, ``filter_trigger``,
``head_group`` — was a second copy of it.

Modifiers :
- ``sticky``      : pins the ``<thead>`` while the body scrolls. Only ever
  applied together with a ``max_height``, because a sticky header with
  nothing to scroll under it does nothing at all.
"""

from __future__ import annotations

from typing import Any

DATATABLE_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-datatable "  # audit marker — cf. tests/audit/checklist.py
            "flex flex-col gap-3 w-full"
        ),
        "toolbar": "flex items-center gap-2 flex-wrap",
        # The search box shouldn't span the table — a full-width text
        # field reads as "type a lot here", which is the wrong promise
        # for a filter. Hence the ceiling at `max-w-xs` (320 px).
        #
        # `flex-1` and NOT `w-full`, and that is the half that counts.
        # Under `flex-wrap`, an overflow makes things WRAP, it does not
        # compress: the search therefore stayed at 320 px at every width
        # (measured from 1400 to 700 px — not a pixel given) and it was
        # the export that paid a whole row as soon as ~1000 px. `flex-1`
        # (basis 0) makes it hold the line whatever happens then grow
        # into the remaining space, so IT is what absorbs the narrowness
        # — it is the bar's most elastic control, the others have a width
        # their text imposes.
        #
        # The floor lives in `sizes[<size>]["search"]`: below ~190 px (at
        # `md`) the placeholder truncates and the field no longer says
        # what it searches, and an elastic WITH NO floor gives a 40 px
        # field before consenting to wrap. It scales because an `lg`
        # table writes bigger: the same number of pixels does not hold
        # the same number of characters there.
        "search": "flex-1 max-w-xs",
        # ``ml-auto``: the export goes to the end of the bar. It is not
        # decorative layout — it is what separates the two natures of
        # control that populate it. On the left you NARROW (search,
        # filters, reset); on the right you TAKE the data OUT. Stuck to
        # the filters, the export read as one of them. THAT is the place
        # to document: the call sites read this slot by its name and have
        # nothing to say about it.
        #
        # ``ml-auto`` and NOT the ``justify-between`` ``footer`` uses two
        # lines below, although it is the same work. The difference is
        # ``flex-wrap``: the footer has exactly two children, the toolbar
        # has a variable number that must stay grouped. Under
        # ``justify-between`` the bar would push the search and the
        # filters to each end whenever room is left. ``ml-auto`` on the
        # last child pushes to the right of THE LINE IT LANDS ON —
        # measured from 1280 to 390 px: wide, it ends the filters' row;
        # narrow, it occupies its own alone, always flush with the right
        # edge. The "two halves" reading therefore holds as long as the
        # bar fits on one line, and degrades cleanly — not into disorder
        # — when it wraps.
        "export": "ms-auto",
        "footer": "flex items-center justify-between gap-3 flex-wrap",
        # Type scale lives in ``sizes[<size>]["info"]`` — a ``text-xs``
        # baked here would be a size the ``size=`` prop could never move.
        "footer_info": "text-muted tabular-nums",
        # A ``ui.button`` in a ``<th>`` has to stop looking like a button
        # and start looking like a header : the cell already owns the
        # padding and the type scale, so the button contributes only the
        # hit area and the affordances (hover, focus ring, keyboard) a
        # bare ``<th>`` has none of.
        #
        # ``px-1 -mx-1`` on purpose : the horizontal padding gives the
        # hover wash some body around the text, and the negative margin
        # cancels it for alignment — so a sortable header still starts on
        # the same pixel as the plain header above it in the column.
        # ``hover:!text-text`` is the affordance that says clickable ; the
        # colour at REST comes from the parent (``color="current"``).
        # ⚠️ The case follows ``Table.head_cell`` — the two MUST stay in
        # agreement, otherwise a sortable column and its static neighbour
        # no longer read as the same header row. The uppercase at 10-12 px
        # was removed from both on 2026-08-06: illegible, and it is
        # exactly what the V1 spec asked to replace with normal case.
        # What distinguishes a header from data is now the WEIGHT and the
        # colour, not the size nor the capitals — the convention of
        # current libraries.
        # Neither ``flex-1`` nor ``min-w-0``: they served the
        # ``head_group`` that shared the cell between the title and a
        # filter trigger. The filter moved to the toolbar, the parent
        # became a bare ``<th>`` again (``table/theme.py`` § head_cell,
        # with no ``display:flex``), and the two tokens no longer acted
        # on anything.
        "head_button": (
            "!justify-start !h-auto !px-1 !py-0.5 -mx-1 "
            "!rounded !text-sm !font-semibold !normal-case !tracking-normal "
            "not-disabled:hover:!text-text gap-1"
        ),
        # Non-sortable headers keep the same box so a sortable and a
        # static column don't sit two pixels apart.
        "head_static": "inline-flex items-center py-0.5",
    },
    # The composed children's own size tokens, derived from the
    # Datatable's — a literal ``Pagination(size="sm")`` would leave the
    # pager the same height on a ``size="lg"`` table. Every row carries
    # the same keys on purpose : a missing one falls back silently,
    # which is how the frozen-child bug started.
    #
    # ⚠️ The sort BUTTON is deliberately absent from this table, and its
    # ``size="xs"`` at the call site is a baselined constant. Table fixes
    # the header type scale (``text-xs uppercase`` in ``head_cell``, the
    # same at every density), so a sortable header that grew with ``size``
    # would no longer match the NON-sortable header beside it. Measured
    # before deciding : with the layout overrides below in place, deriving
    # the button's size changed nothing at all in the browser — one
    # rendered value across sm/md/lg. A derivation that moves nothing is
    # worse than an honest constant, because the test that "proves" it
    # only sees the class string.
    "sizes": {
        # A SINGLE `toolbar` token feeds ALL the bar's controls —
        # search, filters, export — and it goes down as is into the
        # filter combobox's `size=`, whose own `sizes` table scales its
        # panel, its options and its search. Before: the search took
        # `size`, the chip `toolbar_button` and the inner search
        # `filter_check`, so three scales side by side on an `lg` table.
        "sm": {"pager": "sm", "info": "text-xs", "toolbar": "sm",
               "search": "min-w-44"},
        "md": {"pager": "sm", "info": "text-xs", "toolbar": "sm",
               "search": "min-w-48"},
        "lg": {"pager": "md", "info": "text-sm", "toolbar": "md",
               "search": "min-w-56"},
    },
    "modifiers": {
        # ``sticky`` rides on the composed Table via ``classes=`` — the
        # ``<thead>`` is inside it, so the selector reaches down. ``z-10``
        # keeps it above the scrolling rows ; the background is opaque so
        # rows don't show through as they pass under.
        "sticky": (
            "overflow-y-auto "
            "[&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 "
            "[&_thead]:bg-surface"
        ),
    },
    # The sort arrow's three positions. Kept as icon NAMES (not classes)
    # because the affordance is an icon swap, not a style swap.
    "sort_icons": {
        "asc": "arrow-up",
        "desc": "arrow-down",
        # Neutral : a dimmed both-ways arrow that says "this is sortable"
        # without claiming a direction.
        "": "chevrons-up-down",
    },
}
