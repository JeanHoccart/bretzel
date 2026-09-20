"""Default :class:`MonthPicker` theme.

Same silhouette as :class:`DatePicker` — an editable field and an icon
button INSIDE the same focus ring, an anchored popover below. Only the
panel's CONTENT differs (``ui.calendar(mode="month")``), so the class
strings are deliberately the same: two form fields of the same family
must look alike to the pixel.

⚠️ The strings stay COPIED and not shared, on purpose — it is the
repository's rule (`feedback_no_shared_style_tokens`): we harmonise the
convention, we do not factor out the visual tokens. What IS shared is
the mechanics (`inputs/_picker_field.py`).

Slots :
- ``root``          : the wrapper — carries the ``bz-data`` scope
- ``input_frame``   : the visible field (input + buttons, a single ring)
- ``input_field``   : the typable ``<input>``, with no frame of its own
- ``clear_button``  : the ``×``, visible only if there is a value
- ``trigger_button``: the calendar button that opens the panel
- ``button_icon``   : the glyph in both buttons
- ``panel``         : the popover anchored by ``$bz.helpers.floating``
"""

from __future__ import annotations

from typing import Any

MONTH_PICKER_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-month-picker relative flex flex-col w-full",
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
        "panel": (
            "absolute z-40 mt-1 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface shadow-lg "
            # The enter fade, FIELD cadence (75 ms, half the menus').
            # Mechanism of the three classes: a single copy, in
            # ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
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
        "xs": {"input_frame": "h-7", "input_field": "text-xs",
               "clear_button": "w-6", "trigger_button": "w-7",
               "button_icon": "text-xs"},
        "sm": {"input_frame": "h-8", "input_field": "text-xs",
               "clear_button": "w-7", "trigger_button": "w-8",
               "button_icon": "text-sm"},
        "md": {"input_frame": "h-10", "input_field": "text-sm",
               "clear_button": "w-8", "trigger_button": "w-10",
               "button_icon": "text-base"},
        "lg": {"input_frame": "h-12", "input_field": "text-base",
               "clear_button": "w-9", "trigger_button": "w-12",
               "button_icon": "text-lg"},
        "xl": {"input_frame": "h-14", "input_field": "text-lg",
               "clear_button": "w-10", "trigger_button": "w-14",
               "button_icon": "text-xl"},
    },
}
