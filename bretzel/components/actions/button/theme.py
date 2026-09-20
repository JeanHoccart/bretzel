"""Default :class:`Button` theme.

- ``transition-all duration-200 ease-out`` + ``not-disabled:active:scale`` for
  tactile click feedback.
- Solid : brightness + shadow hover lift ; outline / ghost / soft :
  opacity-driven hover (``/10`` → ``/20``).
- Focus ring : ``ring-2 ring-offset-2 ring-{color}/40``.
"""

from __future__ import annotations

from typing import Any

BUTTON_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # Layout
            "inline-flex items-center justify-center "
            # Shape
            "rounded-field font-medium "
            # Motion + tactile feedback
            "transition-all duration-200 ease-out "
            "not-disabled:active:scale-[0.95] "
            # Focus ring
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) "
            # ``loading=True`` also flips the HTML ``disabled`` attr (render())
            # so this one variant covers both states.
            "disabled:opacity-50 disabled:cursor-not-allowed "
            # ── The same state, when the tag is an ``<a>`` ────────────
            # ``ui.button(href=…)`` renders an anchor, and ``:disabled``
            # NEVER matches an ``<a>``: without these twins, a disabled
            # link-button showed at full opacity, normal cursor, and
            # lightened further on hover. The ``render`` sets
            # ``aria-disabled`` + ``tabindex=-1`` and removes the
            # destination — so it does not navigate; what was missing was
            # SHOWING it.
            #
            # ⚠️ The ``!`` is load-bearing, and for a measurable reason
            # that does NOT hold at ``ui.link``. There the variants hover
            # in bare ``hover:*`` (0,2,0), so an
            # ``aria-disabled:hover:*`` (0,3,0) beats them by plain
            # specificity and the theme explains itself. Here the
            # variants write ``not-disabled:hover:*``, which **also**
            # weighs 0,3,0: at equality, it is the order in the sheet
            # that decides, and that order belongs to the compiler.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed "
            "aria-disabled:hover:brightness-100! "
            "aria-disabled:hover:shadow-none! "
            "aria-disabled:active:scale-100!"
        ),
        "icon": "shrink-0",
    },
    "variants": {
        # Solid : full background + foreground colour, hover lifts via
        # brightness + a subtle shadow rather than a flat alpha bump.
        "solid": (
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-sm "
            "not-disabled:hover:brightness-110 not-disabled:hover:shadow-md"
        ),
        # Outline : 2px border so the click target reads as a button
        # even before hover. Hover fills with /10 alpha of the colour.
        "outline": ("border-(length:--bz-stroke-strong) border-(--bz-solid) text-(--bz-text) not-disabled:hover:bg-(--bz-bg)"),
        # Ghost : NO box at rest — coloured text, and a /10 wash on
        # hover. That is a deliberate emphasis level, not a lighter
        # ``soft``, and it constrains WHERE it belongs :
        #
        #   ghost goes INSIDE a container that already draws the box.
        #
        # A menu row, a tinted header cell, a dialog footer next to a
        # ``solid``: the container carries the boundary, the button only
        # brings the click area and the affordances. A STANDALONE
        # control — a toolbar, a lone button at the end of a list — does
        # not have that container: at rest it no longer stands apart from
        # the text, and ``hover:`` cannot make up for that. It is the
        # rule ``theme/tailwind.py`` states at the end of its note on
        # ``@custom-variant hover``: "``hover:`` must still never CARRY
        # an affordance". It does not speak only of touch — before the
        # hover, nobody sees anything, mouse or not.
        #
        # For a discreet standalone control: ``soft`` (washed box) or
        # ``outline`` (bordered box). Giving ``ghost`` a box at rest
        # would melt it into ``soft`` and remove its reason to be — it is
        # the doctrine that was missing, not the CSS.
        #
        # ⚠️ Not gated, and it is measured: forbidding "a box only under
        # hover" in the themes gives 24 occurrences of which 22
        # legitimate (sidebar, dropdown, calendar, pagination — a
        # ``hover:`` that enriches a row in a bounded list is the
        # dominant AND correct pattern). The drift here is "which variant
        # at this call site, given what surrounds it", and that cannot be
        # decided statically: you cannot see in the source whether the
        # parent draws a box. Hence doctrine, and not a test.
        "ghost": ("text-(--bz-text) not-disabled:hover:bg-(--bz-bg)"),
        # Surface: the control reads as a FIELD — the same bordered box
        # as ``ui.input``. It is what was missing for a toolbar mixing a
        # search and buttons to read as ONE family: `soft` gives a wash
        # with no border, `outline` an accented 2 px border, and neither
        # of the two resembles the neighbouring field (`bg-interface` +
        # `border-text/10`).
        #
        # The colour stays a hook (`text-(--bz-text)`) so the "the accent
        # marks the ACTIVE peer" rule goes on applying without changing
        # the box: at rest `current`, active the accent — the geometry
        # does not move.
        "surface": (
            "bg-interface border-(length:--bz-stroke) border-text/10 text-(--bz-text) "
            "not-disabled:hover:bg-text/5"
        ),
        # Soft : muted background, hover bumps to /20.
        "soft": ("bg-(--bz-bg) text-(--bz-text) not-disabled:hover:bg-(--bz-bg-hover)"),
    },
    "sizes": {
        "xs": "h-7 px-2 text-xs gap-1",
        "sm": "h-8 px-3 text-sm gap-1.5",
        "md": "h-10 px-4 text-sm gap-2",
        "lg": "h-12 px-6 text-base gap-2",
        "xl": "h-14 px-8 text-base gap-2.5",
    },
    # No ``modifiers`` map — the disabled visual lives at the root slot via
    # the ``disabled:`` Tailwind variant, reactive through the HTML attribute.
}
