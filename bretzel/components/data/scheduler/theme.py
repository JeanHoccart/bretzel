"""Default :class:`Scheduler` theme.

The week: a grid of hours inside a card, the day names above, small
cards posed at their real time.

Slots :
- ``root``        : the card around the whole grid.
- ``head``        : the row of day headers.
- ``gutter``      : the hours column's width — repeated as a spacer in
  the head and all-day rows, so the columns line up.
- ``day_head``    : one day's header (its name above its number).
- ``day_name``    : the day's short name.
- ``day_number``  : the day's number, in a round cell.
- ``today``       : added to ``day_number`` for today — the solid circle.
- ``all_day_row`` : the row of all-day bars above the grid (gutter + area).
- ``all_day``     : the area the bars are posed in.
- ``all_day_bar`` : one all-day event, across the days it covers.
- ``all_day_title``: its title.
- ``body``        : the grid row (hours + day columns).
- ``hours``       : added to ``gutter`` for the column of hour labels.
- ``hour``        : one hour label of the gutter.
- ``column``      : one day's column.
- ``line_hour``   : the line of a full hour.
- ``line_half``   : the fainter line of a half hour.
- ``event``       : an event card.
- ``event_row``   : the card's line — the title, then the subtitle; it
  wraps when the card is narrow (two events side by side).
- ``event_title`` / ``event_subtitle`` : the card's two texts.
- ``event_line`` / ``event_line_title`` / ``event_line_time`` : a COMPACT
  card's single line (``data-compact``, under ``COMPACT_PX``): the title
  cut with an ellipsis, then the hour.
- ``now``         : the line of the current time.
- ``month_head`` / ``month_head_cell`` : the row of day names of the month.
- ``month``       : the month's weeks; ``month_week`` one week, a row of
  cells under which its all-day bars are posed.
- ``month_cell``  : one day; ``month_number`` its number, with
  ``month_outside`` for a day of the next or previous month (``today``
  stays the solid circle); ``month_list`` its chips; ``month_more`` the
  "+N" of a day holding more than it shows.
- ``chip``        : a timed event in a month cell; ``chip_time`` and
  ``chip_title`` its two texts.
- ``resize``      : the pulled bottom edge of a card (``on_resize=``).
- ``tag``         : the label of the new time, during a gesture.
- ``carrier``     : the hidden inputs the runtime writes a gesture into.

During a gesture the runtime sets ``data-bz-dragging`` on the card held
and ``data-bz-ghost`` on its copy that follows the pointer; the ``event``
slot styles both.

⚠️ **No bar on the card's edge, no coloured outline.** A card is its
colour's soft background, darker on hover, and nothing else. A card's
colour is its bridge class
(``bz-c-<colour>``), set per event at render — the slot reads steps.
"""

from __future__ import annotations

from typing import Any

SCHEDULER_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-scheduler "  # audit marker — cf. tests/audit/checklist.py
            "relative block w-full min-w-0 rounded-box bg-surface text-text "
            "border-(length:--bz-stroke) border-text/10 p-3 sm:p-4"
        ),
        "head": "flex items-end",
        "gutter": "w-12 sm:w-14 shrink-0",
        "day_head": "flex flex-1 min-w-0 flex-col items-center pb-2",
        "day_name": "text-sm text-text/60 uppercase tracking-wider",
        "day_number": (
            "flex size-9 items-center justify-center rounded-full "
            "text-base font-semibold tabular-nums"
        ),
        # The one marked day — ``date=`` is not marked (cf. ``_day_mark``).
        "today": "bz-c-primary bg-(--bz-solid) text-(--bz-on-solid) font-bold",
        "all_day_row": "flex items-start pt-1",
        "all_day": "relative flex-1 min-w-0",
        "all_day_bar": (
            "absolute flex items-center rounded-field px-3 "
            "bg-(--bz-bg) text-(--bz-text) text-sm font-semibold"
        ),
        "all_day_title": "truncate",
        "body": "flex items-start pt-3",
        "hours": "relative",
        "hour": "absolute end-0 pe-2 sm:pe-3 -translate-y-1/2 text-sm text-text/60 tabular-nums",
        "column": "relative flex-1 min-w-0 border-s-(length:--bz-stroke) border-text/10",
        "line_hour": "absolute inset-x-0 border-t-(length:--bz-stroke) border-text/15",
        "line_half": "absolute inset-x-0 border-t-(length:--bz-stroke) border-text/5",
        "event": (
            "absolute overflow-hidden rounded-box px-2.5 py-1.5 "
            "bg-(--bz-bg) text-(--bz-text) hover:bg-(--bz-bg-hover) "
            "transition-colors duration-150 outline-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "[&[role=button]]:cursor-pointer select-none "
            # A finger runs down the week without carrying a card off:
            # the gesture takes a long press (cf. scheduler.js).
            "data-[bz-movable]:touch-pan-y "
            "data-[bz-dragging]:opacity-40 "
            "data-[bz-ghost]:z-30 data-[bz-ghost]:pointer-events-none "
            "data-[bz-ghost]:shadow-lg data-[bz-ghost]:opacity-100 "
            "data-[compact]:flex data-[compact]:items-center data-[compact]:py-0"
        ),
        "event_row": "flex flex-wrap items-baseline justify-between gap-x-2 min-w-0",
        "event_title": "min-w-0 truncate text-sm font-bold",
        "event_subtitle": "min-w-0 truncate text-sm opacity-70",
        "event_line": "flex min-w-0 items-baseline gap-1.5 text-xs leading-tight",
        "event_line_title": "min-w-0 truncate font-bold",
        "event_line_time": "shrink-0 tabular-nums opacity-70",
        "month_head": "flex",
        "month_head_cell": "flex flex-1 min-w-0 justify-center pb-2",
        "month": (
            "flex flex-col border-(length:--bz-stroke) border-text/10 rounded-field "
            "overflow-hidden"
        ),
        "month_week": (
            "relative flex border-t-(length:--bz-stroke) border-text/10 first:border-t-0"
        ),
        "month_cell": (
            "relative flex flex-1 min-w-0 flex-col min-h-28 "
            "border-s-(length:--bz-stroke) border-text/10 first:border-s-0"
        ),
        "month_number": (
            "m-1 flex size-6 items-center justify-center self-end rounded-full "
            "text-sm font-semibold tabular-nums"
        ),
        "month_outside": "text-text/40 font-normal",
        "month_list": "flex min-w-0 flex-col gap-0.5 px-1 pb-1",
        "month_more": "px-1.5 text-xs text-text/60",
        "chip": (
            "flex min-w-0 items-baseline gap-1 rounded-field px-1.5 py-0.5 text-xs "
            "bg-(--bz-bg) text-(--bz-text) hover:bg-(--bz-bg-hover) "
            "transition-colors duration-150 outline-none select-none "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "[&[role=button]]:cursor-pointer data-[bz-movable]:touch-pan-y "
            "data-[bz-dragging]:opacity-40 data-[bz-ghost]:pointer-events-none "
            "data-[bz-ghost]:shadow-lg"
        ),
        "chip_time": "shrink-0 tabular-nums opacity-70",
        "chip_title": "min-w-0 truncate font-semibold",
        "resize": "absolute inset-x-0 bottom-0 h-1.5 cursor-ns-resize",
        "tag": (
            "absolute z-40 pointer-events-none whitespace-nowrap rounded-field "
            "bg-surface text-text text-sm px-2.5 py-0.5 shadow-md "
            "border-(length:--bz-stroke) border-text/15"
        ),
        "carrier": "hidden",
        # The new event traced on the empty grid: the accent, soft, above
        # the cards — no outline, as on the cards.
        "draft": (
            "bz-c-primary absolute z-20 pointer-events-none rounded-box "
            "bg-(--bz-bg) text-(--bz-text) shadow-lg"
        ),
        "now": (
            "bz-c-primary pointer-events-none absolute inset-x-0 z-10 "
            "border-t-(length:--bz-stroke-strong) border-(color:--bz-solid)"
        ),
    },
}
