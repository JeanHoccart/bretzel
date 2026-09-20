"""Default theme for :class:`Pane` — the region that scrolls.

The ``root`` slot carries five utilities, and **two of them cannot be
guessed**. That is the component's reason to be: each cost a measurement
and a ``traps.md`` entry before being written here.

``flex-1`` **and** ``h-full``
    Both, because the parent can have two shapes and the component does
    not know which. In a ``flex-col`` parent, ``flex-basis: 0%``
    replaces the main size and ``height: 100%`` is ignored; in a block
    parent with a defined height (a ``ui.resizable_panel``, for
    instance), ``flex-1`` is inert and it is ``h-full`` that renders.
    Measured in Chromium on all three parent shapes — flex column,
    block, panel: the combination of both scrolls in all three,
    ``flex-1`` alone fails in two (600 px tall, no scrolling),
    ``h-full`` alone misses the remaining space in a flex column.

``min-h-0``
    Load-bearing. Without it, a flex item's automatic minimum height is
    its content's size: the box GROWS instead of scrolling, and nothing
    reports it. Already in ``traps.md`` § *sidebar scroll*.

``[&>*]:shrink-0``
    Load-bearing too, and even less guessable. ``ui.card``'s root
    carries ``overflow-hidden``, so its automatic minimum height is
    ZERO: as soon as the list fills the column, the cards compress below
    their content. Measured on ``examples/crm``: 73 px free against
    34 px constrained, **39 px cut off** — and invisible on the last
    page, which has too few rows to fill. ``traps.md`` § *A column that
    scrolls CRUSHES its items*.

What is **not** here, and why
------------------------------
``pr-1`` — the gutter that keeps the content away from the scrollbar.
Three sites out of seventeen write it, and above all it fights with
``padding=``: ``p-8`` and ``pr-1`` both set ``padding-right``, and the
winner depends on the Tailwind sheet's order, not on the classes'
order. A per-instance setting that breaks a prop stays in ``classes=``.

The ``directions`` / ``alignments`` / ``justifies`` / ``gaps`` tables are
copied from :data:`FLEX_THEME` rather than shared: the repository's
convention is that a theme is self-sufficient, so an override never has
to guess where a value comes from.
"""

from __future__ import annotations

from typing import Any

PANE_THEME: dict[str, Any] = {
    "slots": {
        # ``flex`` alone: the direction comes from the table below
        # (``col`` by default, sealed — a pane is a column).
        "root": "flex flex-1 h-full min-h-0 overflow-y-auto [&>*]:shrink-0",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    # ⚠️ Both CENTRINGS carry the CSS keyword ``safe``, and it is the
    # only place in the catalogue where it counts: a pane SCROLLS
    # (``overflow-y-auto``). Centring content taller than the frame makes
    # it overflow on BOTH sides, yet scrolling never goes back above its
    # origin — so the top part becomes **unreachable**, for good.
    # ``safe`` tells the browser to fall back on ``start`` when it
    # overflows, which is exactly the case where centring harms.
    #
    # Measured on 2026-08-24 on ``auth``'s sign-in page at 1280×600:
    # 732 px of content, a 600 px frame, and **108 px cut off at the
    # top** that nothing allowed you to reach. The symptom designates
    # nothing — the page simply looks truncated, not broken.
    #
    # The bracketed form rather than ``justify-center-safe``: that
    # utility only exists since Tailwind 4.1, and the dev mode's browser
    # compiler may be older. The arbitrary property, for its part, has
    # worked since v3.
    "alignments": {
        "start": "items-start",
        "center": "[align-items:safe_center]",
        "end": "items-end",
        "stretch": "items-stretch",
        "baseline": "items-baseline",
    },
    "justifies": {
        "start": "justify-start",
        "center": "[justify-content:safe_center]",
        "end": "justify-end",
        "between": "justify-between",
        "around": "justify-around",
        "evenly": "justify-evenly",
    },
    "gaps": {
        "none": "gap-0",
        "xs": "gap-1",
        "sm": "gap-2",
        "md": "gap-4",
        "lg": "gap-6",
        "xl": "gap-8",
    },
    # Same scale as ``ui.card`` — the breathing room of a content region
    # and a card's are compared by eye in the same view, so two competing
    # scales would show.
    "paddings": {
        "none": "",
        "xs": "p-2 sm:p-3",
        "sm": "p-3 sm:p-4",
        "md": "p-4 sm:p-6",
        "lg": "p-6 sm:p-8",
        "xl": "p-8 sm:p-10",
    },
    # No ``wrap`` key: the prop is SEALED on the component, so the table
    # would be dead theme — and it came out in ``bretzel describe pane``,
    # which made visible a prop refused at the call. Exactly what
    # ``SEALED_PROPS`` exists to avoid.
    # Copied from :data:`FLEX_THEME` like the neighbouring tables — a
    # theme is self-sufficient in this repository. The three copies are
    # kept identical by ``test_a_flex_family_declares_every_table``.
    "grows": {
        "equal": "*:grow *:basis-0",
        "12rem": "*:grow *:basis-48",
        "16rem": "*:grow *:basis-64",
        "20rem": "*:grow *:basis-80",
    },
}
