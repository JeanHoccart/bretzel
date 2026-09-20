"""Default :class:`Grid` theme.

Pure layout primitive — root carries ``grid``, ``cols`` resolves to a
``grid-cols-N`` (or responsive variants) via the inline parser in
:mod:`bretzel.components.layout.grid.grid`, ``gap`` maps onto the
standard 5-palier scale (matching :class:`Flex` / :class:`VStack`).
"""

from __future__ import annotations

from typing import Any

GRID_THEME: dict[str, Any] = {
    "slots": {
        "root": "grid",
    },
    #: ``min_col=`` — the grid counts its columns ITSELF.
    #:
    #: ``repeat(auto-fit, minmax(X, 1fr))`` is the canonical CSS idiom of
    #: the responsive grid with no media query: the browser fits as many
    #: columns as it can while giving each at least ``X``, and wraps the
    #: rest. Precedent: Chakra's ``minChildWidth``, which translates
    #: exactly into this.
    #:
    #: The defect it closes, measured on 2026-08-25 on the CRM's
    #: "Display" row, in a 1024 px container — the real content width,
    #: side bar deducted ::
    #:
    #:     cols={"base":1,"md":2,"xl":4}   4 columns, 244 px cells,
    #:                                     the toggle_group (256) 11.9 outside
    #:     min_col="16rem"                 3 columns of 331 px, nothing outside
    #:
    #: And the half you do not see: an ``xl:`` prefix reads the WINDOW's
    #: width, not the grid's. Shrinking the window to 700 px turned the
    #: grid into ONE column of 1024 — the container had not moved.
    #: ``auto-fit`` reads the real room, so it does not have that offset.
    #:
    #: A CLOSED table, like ``grows``: each value is a WHOLE class, hence
    #: visible to the production Tailwind compiler. A width assembled in
    #: an f-string would render identical HTML in dev and no rule at all
    #: in prod (memory ``project_assembled_tailwind_class_dev_only``).
    #:
    #: ``auto-fit`` and not ``auto-fill``: the first collapses empty
    #: tracks, so the present columns share all the room. With
    #: ``auto-fill``, two fields in a wide container would stay stuck to
    #: the left with empty space on the right.
    "min_cols": {
        "12rem": "grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]",
        "16rem": "grid-cols-[repeat(auto-fit,minmax(16rem,1fr))]",
        "20rem": "grid-cols-[repeat(auto-fit,minmax(20rem,1fr))]",
        "24rem": "grid-cols-[repeat(auto-fit,minmax(24rem,1fr))]",
    },
    # Gap palier — same vocabulary as Flex / VStack so layouts mix and
    # match without surprise.
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
}
