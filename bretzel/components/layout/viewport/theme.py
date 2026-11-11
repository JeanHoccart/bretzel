"""Default theme for :class:`Viewport` — the full-screen frame.

``fixed inset-0 w-full overflow-hidden``, and the ``fixed`` is the only
utility that really counts.

Why ``fixed inset-0`` and most certainly NOT ``h-screen``
-----------------------------------------------------------
``h-screen`` leaves the frame IN the document's flow. A descendant that
scrolls then inflates ``html.scrollHeight`` beyond ``clientHeight``, and
the browser renders a **second scrollbar** at the viewport level.
``position: fixed`` takes the frame out of the flow —
``html.scrollHeight`` falls back to ``clientHeight``, and only the
intended bar remains, the
:class:`~bretzel.components.layout.pane.Pane`'s.

⚠️ ``overflow-hidden`` + ``min-h-0`` are NOT enough. The trap of that
belief is that it is true on SHORT pages: the inflation is zero as long
as the content fits on screen, hence the feeling that ``h-screen`` works.

The flex tables are copied from :data:`FLEX_THEME` rather than shared —
a theme in this repository is self-sufficient, so an override never has
to guess where a value comes from.
"""

from __future__ import annotations

from typing import Any

VIEWPORT_THEME: dict[str, Any] = {
    "slots": {
        # ``flex`` alone: the direction comes from the table below.
        "root": "flex fixed inset-0 w-full overflow-hidden",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    # ⚠️ Both centrings carry ``safe``, as in ``ui.pane`` and for a
    # WORSE reason: the frame is ``overflow-hidden``, so content centred
    # taller than the screen is cut off at both ends and **nothing
    # scrolls** to go and get it. ``safe`` falls back on ``start`` when
    # it overflows, and changes nothing the rest of the time.
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
        "xs": "gap-(--bz-gap-1)",
        "sm": "gap-(--bz-gap-2)",
        "md": "gap-(--bz-gap-4)",
        "lg": "gap-(--bz-gap-6)",
        "xl": "gap-(--bz-gap-8)",
    },
    "wrap": "flex-wrap",
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
