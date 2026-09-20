"""Default :class:`TimePicker` theme.

Same silhouette as :class:`DatePicker` — an editable field and an icon
button INSIDE the same focus ring, an anchored popover below — but the
panel is not a grid: it is **two snapping columns**, hours and minutes.

Why home-made columns and not an ``<input type="time">``: a native
widget is not themable and completely changes look between Chrome,
Safari and Android. It is the lesson paid on the Carousel's scrollbar,
more visibly so.

The columns reuse two already-written mechanics:

- ``bz-no-scrollbar`` (a framework CSS hook, ``theme/css.py``) — a
  24-hour column scrolls, and its native bar would be the component's
  only unthemed element;
- ``snap-y snap-mandatory`` + ``snap-center`` — the same CSS snapping as
  the Carousel's track, so the scroll stops on a value and never between
  two.

Slots :
- ``root``          : the wrapper — carries the ``bz-data`` scope
- ``input_frame``   : the visible field (input + buttons, a single ring)
- ``input_field``   : the typable ``<input>``, with no frame of its own
- ``clear_button``  : the ``×``, visible only if there is a value
- ``trigger_button``: the clock button that opens the panel
- ``button_icon``   : the glyph in both buttons
- ``panel``         : the popover anchored by ``$bz.helpers.floating``
- ``columns``       : the row of the two columns
- ``column``        : one snapping scrolling column
- ``cell``          : one hour or minute cell
- ``column_label``  : the "Hours" / "Minutes" header
"""

from __future__ import annotations

from typing import Any

TIME_PICKER_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` and not ``w-fit``: the field fills its parent like
        # any other form input, so it lines up with its neighbours in a
        # grid and never overflows its cell (the defect measured on
        # date_picker before its correction).
        "root": "bz-time-picker relative flex flex-col w-full",
        "input_frame": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text transition-all duration-200 "
            "focus-within:border-(--bz-solid) focus-within:ring-2 "
            "focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        "input_field": (
            "flex-1 min-w-0 px-3 bg-transparent text-text "
            "placeholder:text-muted/60 outline-none "
            "rounded-l-field disabled:cursor-not-allowed"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted/60 not-disabled:hover:text-text outline-none "
            "transition-colors disabled:opacity-50 "
            "disabled:cursor-not-allowed"
        ),
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-(--bz-text) not-disabled:hover:bg-(--bz-bg) rounded-r-field "
            "outline-none focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) transition-colors "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        "button_icon": "inline-flex shrink-0 text-current",
        # Positioned by ``$bz.helpers.floating`` (``position: fixed`` +
        # inline coordinates). NO ``left-0`` / ``right-0``: under fixed
        # position they fight the inline coordinates (cf. traps.md
        # § "panel left-0 right-0 under floating").
        "panel": (
            "absolute z-40 mt-1 p-2 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface shadow-lg "
            # The enter fade, FIELD cadence (75 ms, half the menus').
            # Mechanism of the three classes: a single copy, in
            # ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
        "columns": "flex gap-1",
        # ``bz-no-scrollbar``: a framework CSS hook, not a Tailwind
        # utility — the equivalent arbitrary variants do not compile
        # (measured on the Carousel).
        "column": (
            "bz-no-scrollbar flex flex-col gap-0.5 overflow-y-auto "
            "snap-y snap-mandatory scroll-pt-1"
        ),
        "column_label": (
            "sticky top-0 z-10 bg-interface text-muted font-medium "
            "text-center pb-1"
        ),
        "cell": (
            "snap-center shrink-0 rounded-selector text-center tabular-nums "
            "cursor-pointer transition-colors duration-150 "
            "not-disabled:hover:bg-(--bz-bg) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-inset focus-visible:ring-(--bz-focus) "
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "data-[selected=true]:font-semibold "
            "disabled:opacity-40 disabled:cursor-not-allowed "
            "disabled:hover:bg-transparent"
        ),
    },
    # The step's height lives on ``input_frame`` — the frame, which
    # carries the border. Under ``box-sizing: border-box``, ``h-10`` on
    # the frame is 40 px border included, like ``ui.input`` which sets
    # height and border on the SAME element. Set on the child, it gave
    # 40 px + the frame's 2 px: **42 px**, 2 px more than any other
    # control, at all five steps. Measured on 2026-08-23, guarded by
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    # The children therefore no longer have an ``h-*``: the frame is
    # ``items-stretch``, they fill its inner height.
    "sizes": {
        "xs": {
            "input_frame": "h-7",
            "input_field": "text-xs",
            "clear_button": "w-6",
            "trigger_button": "w-7",
            "button_icon": "text-xs",
            "column": "max-h-40 w-12",
            "column_label": "text-[10px]",
            "cell": "py-0.5 text-xs",
        },
        "sm": {
            "input_frame": "h-8",
            "input_field": "text-xs",
            "clear_button": "w-7",
            "trigger_button": "w-8",
            "button_icon": "text-sm",
            "column": "max-h-44 w-14",
            "column_label": "text-[10px]",
            "cell": "py-1 text-xs",
        },
        "md": {
            "input_frame": "h-10",
            "input_field": "text-sm",
            "clear_button": "w-8",
            "trigger_button": "w-10",
            "button_icon": "text-base",
            "column": "max-h-56 w-16",
            "column_label": "text-xs",
            "cell": "py-1.5 text-sm",
        },
        "lg": {
            "input_frame": "h-12",
            "input_field": "text-base",
            "clear_button": "w-9",
            "trigger_button": "w-12",
            "button_icon": "text-lg",
            "column": "max-h-64 w-20",
            "column_label": "text-sm",
            "cell": "py-2 text-base",
        },
        "xl": {
            "input_frame": "h-14",
            "input_field": "text-lg",
            "clear_button": "w-10",
            "trigger_button": "w-14",
            "button_icon": "text-xl",
            "column": "max-h-72 w-24",
            "column_label": "text-base",
            "cell": "py-2.5 text-lg",
        },
    },
}
