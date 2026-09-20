"""Default :class:`Flex` theme.

Shared by :class:`VStack`, :class:`HStack` — the
shortcut classes inherit and only differ on which ``direction`` /
``axis`` defaults are baked in.
"""

from __future__ import annotations

from typing import Any

FLEX_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex",
    },
    "directions": {
        "row": "flex-row",
        "col": "flex-col",
        "row-reverse": "flex-row-reverse",
        "col-reverse": "flex-col-reverse",
    },
    #: ⚠️ ``center`` carries ``safe``, as in :data:`PANE_THEME` and
    #: :data:`VIEWPORT_THEME`. Centring content taller than its frame
    #: makes it overflow on BOTH sides, and scrolling never goes back
    #: above its origin: the top becomes **unreachable**, not "hard to
    #: see". Measured on 2026-08-24 on ``examples/auth``'s sign-in page —
    #: 732 px of content in 600, and at ``scrollTop = 0`` the content
    #: started at −108 px.
    #:
    #: This table declares no overflow, and that is precisely why it
    #: needed it: the scrolling is set at the CALL SITE
    #: (``ui.vstack(classes="… overflow-y-auto")``, ``outlet``'s recipe
    #: and one of the CRM's drop zones), so no local reading could bring
    #: the two together. ``safe`` changes NOTHING when the content fits —
    #: so there is no reason to centre without it.
    #:
    #: The bracketed form and not ``items-center-safe``: that utility
    #: only exists since Tailwind 4.1, and the dev mode's browser
    #: compiler may be older.
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
    "wrap": "flex-wrap",
    #: ``grow=`` — how the direct children share the MAIN axis. Absent
    #: by default: a stack that asks for nothing emits none of these
    #: classes.
    #:
    #: The keys name the BASIS, not a step of the ``xs..xl`` scale. It is
    #: deliberate: ``size="md"`` and ``grow="md"`` would have named two
    #: unrelated things, and the reader of a call would have had no way
    #: of telling them apart. Here ``grow="16rem"`` reads as it acts.
    #:
    #: A CLOSED table, and that is what makes it safe: each value is a
    #: WHOLE class, hence visible to the production Tailwind compiler. A
    #: basis assembled in an f-string (``f"*:basis-{n}"``) would render
    #: identical HTML in dev and no style in prod (memory
    #: ``project_assembled_tailwind_class_dev_only``). For a value
    #: outside the table, it is ``classes=`` at the call site — tier 2.
    "grows": {
        # Strictly equal shares: the basis is zero, so the content does
        # not weigh in the split. It is Mantine's ``<Group grow>``, and
        # the only mode that ignores ``wrap=``.
        "equal": "*:grow *:basis-0",
        "12rem": "*:grow *:basis-48",
        # The only value the repository really used: the three
        # ``BAR_FIELD = "basis-64 grow"`` of examples/ were this one.
        "16rem": "*:grow *:basis-64",
        "20rem": "*:grow *:basis-80",
    },
}
