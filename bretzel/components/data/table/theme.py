"""Default :class:`Table` theme.

Clean tabular layout : soft border around the whole table, light header
tint, and ONE opinionated row treatment — zebra stripes + a hover
highlight, always on. Matches the Card / Input radius family so it sits
naturally next to the rest of the design system.

No per-instance ``striped`` / ``hover`` / ``bordered`` / ``compact``
props : striped + hover are the baked-in look, vertical rules go through
a ``classes=`` override, and density uses the standard ``size=`` scale.

Slots :
- ``root``     : the scroll container ``<div>`` wrapping the table — the
  visual shell (rounded card + border) AND the horizontal-scroll viewport.
  A ``<table>`` can't scroll its own content, so this wrapper is what makes
  a wide table responsive : it stays put and scrolls sideways instead of
  clipping columns or forcing the whole page wider. It is the component's
  TRUE root — ``id`` / ``classes=`` / ``attrs=`` / ``visible`` / ``tooltip``
  all land here.
- ``table``    : the ``<table>`` element (``w-full`` + zebra + hover). Fills
  the wrapper when narrow ; grows past it (→ the wrapper scrolls) when the
  columns need more room than the viewport gives.
- ``head``     : the ``<thead>`` row container
- ``head_cell``: each ``<th>`` cell (padding comes from ``sizes``)
- ``body``     : the ``<tbody>``
- ``row``      : each ``<tr>`` in the body
- ``cell``     : each ``<td>`` (padding comes from ``sizes``)
- ``empty_cell``: the "no rows" placeholder row (``p-0`` — keeps its own
  spacing, deliberately NOT sized so the size scale can't crush it)

``sizes`` drives the cell density (``sm`` / ``md`` / ``lg``) — padding
lives here and is composed onto the head / body cells at render time
(NOT as a root ``[&_td]`` modifier, which would also hit the empty
cell's ``p-0``).

Modifiers :
- ``clickable``: cursor + select affordance for interactive rows

The ``head`` background tint is colour-driven (``bg-<color>/5``) and so
is computed at render time from the ``color`` prop, not baked here — it
needs the live colour token (cf. ``Table.render``).

⚠️ Hover vs striped specificity ("hover only on 1 row out of 2" bug) :
the striped ``nth-child(even)`` and the ``hover`` selectors have EQUAL
specificity (both 0,2,2), so on an even row the later source rule wins
and striped beats hover — only ODD rows showed a hover. Fix : ``!important``
on the hover so it wins on every row. (cf. traps.md.)
"""

from __future__ import annotations

from typing import Any

TABLE_THEME: dict[str, Any] = {
    "slots": {
        # Scroll container = visual shell (border + rounding) AND the
        # horizontal-scroll viewport. ``overflow-x-auto`` gives a wide table
        # a sideways scrollbar instead of clipping columns, and clips the
        # inner table's corners to the ``rounded-box``. ``max-w-full`` stops
        # the table inside dragging the container past its parent.
        "root": (
            "bz-table "  # audit marker — cf. tests/audit/checklist.py
            "max-w-full overflow-x-auto "
            "border-(length:--bz-stroke) border-text/10 rounded-box"
        ),
        # The ``<table>``. ``border-separate`` + zero spacing keeps the
        # rounded corners clean. Zebra + hover are baked in (hover uses
        # ``!important`` to beat the equal-specificity striped rule on even
        # rows — see the module docstring). ``w-full`` fills the wrapper
        # when narrow ; the intrinsic width takes over (→ scroll) when wide.
        "table": (
            "w-full text-sm text-text "
            "border-separate border-spacing-0 "
            "[&>tbody>tr:nth-child(even)]:bg-text/[0.02] "
            "[&>tbody>tr:hover]:!bg-text/[0.05]"
        ),
        # Structural only — the colour tint (``bg-<color>/5``) is added
        # at render time so the header follows the ``color`` prop.
        "head": "",
        # Padding is added per-size at render time (see ``sizes``).
        # ⚠️ Casse NORMALE, et c'est un choix mesuré. L'en-tête était en
        # ``text-xs uppercase tracking-wide`` : à 12 px, des capitales
        # espacées se lisent nettement moins vite qu'un mot ordinaire, et
        # le spec DataTable de V1 demandait déjà de les remplacer pour
        # cette raison. Ce qui sépare un en-tête d'une donnée est le POIDS
        # et la couleur — la convention des bibliothèques actuelles.
        #
        # Ce slot est la SOURCE de la décision : ``Datatable.head_button``
        # la recopie pour que sa colonne triable s'aligne sur sa voisine
        # statique. Changer l'une sans l'autre casse cet alignement.
        "head_cell": (
            "text-start text-sm font-semibold "
            "text-text/70 border-b-(length:--bz-stroke) border-text/10 whitespace-nowrap"
        ),
        "body": "",
        "row": (
            "transition-colors duration-100"
        ),
        # Padding is added per-size at render time (see ``sizes``).
        "cell": (
            "border-b-(length:--bz-stroke) border-text/5 align-middle"
        ),
        # The empty-state lives in a full-width cell that hosts the
        # ``ui.empty_state`` component — ``p-0`` (and NOT sized) so the
        # component owns its own spacing.
        "empty_cell": "p-0 border-b-(length:--bz-stroke) border-text/5",
    },
    # Cell density — composed onto head / body cells at render time.
    "sizes": {
        "sm": "px-3 py-1.5",
        "md": "px-4 py-2.5",
        "lg": "px-5 py-3.5",
    },
    "modifiers": {
        # Clickable rows : pointer affordance + no text selection on the
        # double-click that often follows a row click.
        "clickable": "[&>tbody>tr]:cursor-pointer [&>tbody>tr]:select-none",
    },
    # Per-column alignment modifiers — applied on the th + td of the
    # corresponding column.
    "aligns": {
        "left":   "text-left",
        "center": "text-center",
        "right":  "text-right",
    },
}
