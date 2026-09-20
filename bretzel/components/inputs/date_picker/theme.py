"""Default :class:`DatePicker` theme.

Single-field layout : the visible ``<input>`` accepts keyboard typing
AND the calendar icon button lives **inside** the same focus ring so
the whole row reads as one native-feeling date field. The popover
hangs from the bottom of the wrapper when ``open``.
"""

from __future__ import annotations

from typing import Any

DATE_PICKER_THEME: dict[str, Any] = {
    "slots": {
        # Outer ``bz-data`` wrapper — relative anchor for the popover.
        # ``w-full`` (not ``w-fit``) : the field fills its parent like every
        # other form input (input / number_input / select / combobox), so it
        # aligns with its siblings in a grid / form_field and NEVER overflows
        # its cell. With ``w-fit`` the root sized to its content's max-content
        # (the ~20ch ``<input>`` + the icon buttons) and grew past a
        # constrained cell — worse once a value showed the ``×`` clear button
        # (``shrink-0``), stretching the whole row. The inner ``<input>`` is
        # ``flex-1 min-w-0`` so it shrinks to fit instead.
        "root": (
            "bz-date-picker relative flex flex-col w-full"
        ),
        # The visible field — looks like ui.input from the outside.
        # ``focus-within:*`` lights the ring when EITHER the typing
        # input or one of the inner buttons gets focus.
        "input_frame": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text transition-all duration-200 "
            "focus-within:border-(--bz-solid) focus-within:ring-2 "
            "focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        # The transparent typeable input — no frame of its own.
        # ``h-*`` / ``text-*`` live in the per-size map below so ``size=``
        # actually propagates to the field — without this split every
        # size palier renders identical.
        "input_field": (
            "flex-1 min-w-0 px-3 bg-transparent text-text "
            "placeholder:text-muted/60 outline-none "
            "rounded-l-field disabled:cursor-not-allowed"
        ),
        # The "×" button — only visible when a value is set.
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted/60 not-disabled:hover:text-text outline-none "
            "transition-colors disabled:opacity-50 "
            "disabled:cursor-not-allowed"
        ),
        # The calendar icon button — opens / toggles the popover.
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-(--bz-text) not-disabled:hover:bg-(--bz-bg) rounded-r-field "
            "outline-none focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) transition-colors "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # The icon glyph inside clear / trigger buttons.
        "button_icon": (
            "inline-flex shrink-0 text-current"
        ),
        # Popover panel that hosts the <bz-calendar>. Positioned by the V3
        # ``$bz.helpers.floating`` helper (``position: fixed`` + inline
        # ``top``/``left`` with main-axis flip + cross-axis clamp), same as
        # Select / Combobox / Popover — so it best-fits and never clips at a
        # viewport edge. NO ``top-full left-0`` : those are the old
        # ``absolute``-model anchors ; under fixed positioning the leftover
        # ``left-0`` (and any ``right-0``) fights the inline coords (cf.
        # traps.md § "panel left-0 right-0 under floating").
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
    # ── Size steps ───────────────────────────────────────────────
    # The height lives on ``input_frame``, NOT on ``input_field`` — and
    # it is load-bearing. The frame carries the border; under
    # ``box-sizing: border-box`` (Tailwind's preset), an ``h-10`` set on
    # the frame is 40 px border included, exactly like ``ui.input``,
    # which sets its height and its border on the SAME element. Set on
    # the child, it gave 40 px + the frame's 2 px: **42 px**, that is
    # 2 px more than any other control, at each of the five steps.
    # Measured in Chromium on 2026-08-23, guarded by
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    #
    # The children therefore no longer have an ``h-*``: the frame is
    # ``items-stretch``, they fill its inner height. Giving them one back
    # would make them overflow the frame.
    "sizes": {
        "input_frame": {
            "xs": "h-7",
            "sm": "h-8",
            "md": "h-10",
            "lg": "h-12",
            "xl": "h-14",
        },
        "input_field": {
            "xs": "text-xs",
            "sm": "text-xs",
            "md": "text-sm",
            "lg": "text-base",
            "xl": "text-lg",
        },
        "clear_button": {
            "xs": "w-6",
            "sm": "w-7",
            "md": "w-8",
            "lg": "w-9",
            "xl": "w-10",
        },
        "trigger_button": {
            "xs": "w-7",
            "sm": "w-8",
            "md": "w-10",
            "lg": "w-12",
            "xl": "w-14",
        },
        "button_icon": {
            "xs": "text-xs",
            "sm": "text-sm",
            "md": "text-base",
            "lg": "text-lg",
            "xl": "text-xl",
        },
    },
}
