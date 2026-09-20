"""Default :class:`Calendar` theme.

Five visual zones :

- ``root`` : grid layout (header + weekday row + 6 week rows)
- ``header`` : month label + prev/next buttons row
- ``nav_button`` : the chevron buttons in the header
- ``month_label`` : centered ``"March 2026"`` text (the defaults are
  ENGLISH — cf. ``calendar.py``; other languages go through
  ``month_names=``)
- ``weekday_row`` / ``weekday`` : the ``Sun Mon Tue Wed Thu Fri Sat``
  strip (English defaults, overridable via ``weekday_names=``)
- ``week_row`` : flex row of 7 day cells
- ``month_grid`` / ``month_cell`` : the YEAR grid of ``month`` mode
  (12 cells, 3 × 4) — a second kind of grid, rendered instead of
  ``weekday_row`` + ``week_row``, never in addition
- ``day_cell`` : each clickable day button
  - ``data-selected="true"`` : single-pick / range endpoints
  - ``data-in-range="true"`` : middles of an active range
  - ``data-today="true"`` : today (subtle ring)
  - ``data-outside="true"`` : day belonging to prev/next month (muted)
  - ``aria-disabled="true"`` : disabled day (min/max/disabled_dates)
"""

from __future__ import annotations

from typing import Any

CALENDAR_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ⚠️ NO ``w-fit``: the width comes from the sizes table
            # (``sizes[<size>]["root"]``), and it is a fix, not a
            # preference. With ``w-fit`` the root was
            # ``max(header, grid)`` — yet the month's label is text of
            # variable width, so "septembre" widened the whole calendar.
            # Measured on 2026-08-25: 278 px in August, 292.8 px in
            # September, and **the "next month" arrow moved by 14.8 px**.
            # You click, the target moves, you have to re-aim. (The
            # height, for its part, did not move: the grid always
            # completes its 6 weeks.)
            "bz-calendar inline-flex flex-col gap-2 "
            "h-fit max-w-full "
            "p-3 rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            "select-none "
            # Disabled feedback : whole grid fades + cursor reflects it.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``min-w-0``: without it, a flex child refuses to shrink below
        # its content size, and the label's ``truncate`` would never
        # fire — the header would overflow the fixed width instead of
        # folding into it.
        # ``gap-1.5`` and not ``gap-2``: three 6 px spaces instead of 8
        # give 6 px to the label, enough for "septembre" NOT to trigger
        # the ``truncate`` at ``md``. The truncate stays the net — a
        # language with longer months will find it.
        "header": "flex items-center justify-between gap-1.5 w-full min-w-0",
        "nav_button": (
            # Size (``w-8 h-8`` md) in ``sizes``, not here — cf. weekday.
            "inline-flex shrink-0 items-center justify-center rounded-selector "
            "text-text/70 not-disabled:hover:bg-text/5 not-disabled:hover:text-text "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "transition-colors"
        ),
        "month_label": "font-semibold text-text truncate min-w-0",
        "weekday_row": "grid grid-cols-7 gap-0",
        "weekday": (
            # ⚠️ No SIZE token here (w-/h-/text-<size>): it lives in
            # ``sizes[<size>]["weekday"]``, ``md`` included. Putting them
            # in the slot makes them STACK with the table → a collision
            # on the same element (Tailwind decides by its sheet's order,
            # unpredictable winner). Cf. traps.md § "size=: slot ↔ table
            # collision".
            "flex items-center justify-center "
            "font-medium text-text/50 uppercase tracking-wider"
        ),
        # The dot of a marked cell. ABSOLUTE, and that is the point:
        # placed in the flow, it would turn the cell into a column and
        # shift the day number of EVERY cell, marked or not.
        # ``day_cell`` already carries ``relative``.
        #
        # ``pointer-events-none``: the whole cell is the button, the dot
        # must not eat the click. ``[&[data-selected=true]]`` brings it
        # back to the foreground on a selected day, whose background is
        # already the accent colour — otherwise it would disappear into
        # it.
        "day_mark": (
            "pointer-events-none absolute left-1/2 -translate-x-1/2 "
            "rounded-full bg-(--bz-solid) "
            "[[data-selected=true]_&]:bg-(--bz-on-solid)"
        ),
        "week_row": "grid grid-cols-7 gap-0",
        # ── ``month`` mode: a YEAR grid, 3 × 4 ──────────────────────
        # 3 columns and not 4: the labels are words ("August"), not
        # two-digit numbers, so they need width. Four columns would force
        # abbreviation, and abbreviating "Juin" gains nothing.
        "month_grid": "grid grid-cols-3 gap-1 p-1",
        "month_cell": (
            "inline-flex items-center justify-center rounded-selector "
            "text-text not-disabled:hover:bg-text/5 "
            "transition-colors duration-150 cursor-pointer "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus) "
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:font-semibold "
            "data-[current=true]:ring-1 data-[current=true]:ring-text/30 "
            "aria-disabled:opacity-40 aria-disabled:cursor-not-allowed "
            "aria-disabled:hover:bg-transparent"
        ),
        "day_cell": (
            # Same — the size (``w-9 h-9 text-sm`` for md) lives in
            # ``sizes``, not here.
            "relative inline-flex items-center justify-center "
            "rounded-selector "
            "text-text "
            "not-disabled:hover:bg-text/5 "
            "data-[outside=true]:text-text/30 "
            "data-[today=true]:ring-1 data-[today=true]:ring-text/30 "
            # Range middles : same ``--bz-bg`` wash, flat sides so they
            # tile seamlessly into the endpoints.
            "data-[in-range=true]:bg-(--bz-bg) "
            "data-[in-range=true]:rounded-none "
            # Range endpoints : flat the side that faces the in-range
            # so the bar reads as one continuous shape. Keep the
            # outer-facing side rounded.
            "data-[range-start=true]:rounded-r-none "
            "data-[range-end=true]:rounded-l-none "
            # Selected (single or range endpoints) wins last.
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:enabled:hover:bg-(--bz-solid) "
            # Per-cell disable (min/max/disabled_dates) rides
            # ``aria-disabled`` ; a WHOLE-calendar ``disabled`` stamps
            # the native ``disabled`` attr on every cell (JS ``_render``)
            # — mirror both so the cursor/opacity feedback matches the
            # convention (Button / Select : ``disabled:cursor-not-allowed``)
            # in both cases.
            "aria-disabled:opacity-30 aria-disabled:cursor-not-allowed "
            "aria-disabled:enabled:hover:bg-transparent "
            "disabled:opacity-30 disabled:cursor-not-allowed "
            "transition-colors"
        ),
        # ⚠️ The ``event_dot`` slot was REMOVED on 2026-08-01: nothing
        # read it (neither ``calendar.py``, nor ``07_calendar.js``, nor
        # the ``theme_blob``), and this file's docstring attached it to a
        # "view mode" that does not exist (``_VALID_MODES = ("picker",
        # "range")``). It will come back with a real
        # ``ui.event_calendar``.
    },
    # 5 paliers — same scale as every other input (Input / Button /
    # Select / NumberInput / Slider / Combobox / Avatar). Each entry
    # overrides the slot baselines (which target ``md``).
    "sizes": {
        "xs": {
            # 224 px and not the grid's 192 (7 × 24 + 24): at this step
            # the HEADER is wider than it is. Measured in French,
            # "septembre": 197 px of content against 168 of grid, and the
            # excess crushed the month selector's chevron —
            # "septembre2026" stuck together. The grid's tracks being
            # ``1fr``, the cells absorb the surplus; ``w-6`` stays their
            # floor.
            "root": "w-56",
            "day_mark": "w-1 h-1 bottom-0.5",
            "day_cell": "w-6 h-6 text-[10px]",
            "month_cell": "h-7 text-[10px]",
            "weekday": "w-6 h-5 text-[9px]",
            "nav_button": "w-6! h-6!",
            "month_label": "text-[11px]",
            "chevron": "text-[10px]",
        },
        "sm": {
            # 7 × 32 + 24 = 248 px: the grid, plus the ``p-3`` of both edges.
            "root": "w-62",
            "day_mark": "w-1 h-1 bottom-1",
            "day_cell": "w-8 h-8 text-xs",
            "month_cell": "h-8 text-xs",
            "weekday": "w-8 h-6 text-[10px]",
            "nav_button": "w-7! h-7!",
            "month_label": "text-xs",
            "chevron": "text-xs",
        },
        "md": {
            # 7 × 36 + 24 = 276 px: the grid, plus the ``p-3`` of both edges.
            "root": "w-69",
            # The md step lives in the table like the other sizes (in
            # the slots, it would stack with them on the same element).
            "day_mark": "w-1.5 h-1.5 bottom-1",
            "day_cell": "w-9 h-9 text-sm",
            "month_cell": "h-9 text-sm",
            "weekday": "w-9 h-7 text-xs",
            "nav_button": "w-8! h-8!",
            "month_label": "text-sm",
            "chevron": "text-sm",
        },
        "lg": {
            # 7 × 44 + 24 = 332 px: the grid, plus the ``p-3`` of both edges.
            "root": "w-83",
            "day_mark": "w-1.5 h-1.5 bottom-1.5",
            "day_cell": "w-11 h-11 text-base",
            "month_cell": "h-11 text-base",
            "weekday": "w-11 h-9 text-sm",
            "nav_button": "w-9! h-9!",
            "month_label": "text-base",
            "chevron": "text-base",
        },
        "xl": {
            # 7 × 13 + 6 = 97 steps: the grid, plus the ``p-3`` of both
            # edges.
            "root": "w-97",
            "day_mark": "w-2 h-2 bottom-1.5",
            "day_cell": "w-13 h-13 text-lg",
            "month_cell": "h-13 text-lg",
            "weekday": "w-13 h-10 text-base",
            # ⚠️ Twelve steps (36 px) and not eleven: this button's
            # chevron is a ``ui.icon`` at the ``xl`` step, that is to say
            # ``text-4xl`` — a 32 px glyph, which does not fit in 33 px
            # minus the border. Measured: 1.5 px outside.
            "nav_button": "w-12! h-12!",
            "month_label": "text-lg",
            "chevron": "text-lg",
        },
    },
}
