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
            "bg-interface text-text transition duration-200 "
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
        # Neutral at rest, ink on hover — never the field's colour: the
        # accent marks the ACTIVE (the field's focus ring says it), not a
        # glyph that sits there (``components.md`` § R1).
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted not-disabled:hover:text-text not-disabled:hover:bg-text/5 rounded-r-field "
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
        # ``top``/``left`` with its side, the opposite, then the others ; both axes clamped), same as
        # Select / Combobox / Popover — so it best-fits and never clips at a
        # viewport edge. NO ``top-full left-0`` : those are the old
        # ``absolute``-model anchors ; under fixed positioning the leftover
        # ``left-0`` (and any ``right-0``) fights the inline coords.
        "panel": (
            "absolute z-40 mt-1 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-surface shadow-lg "
            # The enter fade, FIELD cadence (75 ms, half the menus').
            # Mechanism of the three classes: a single copy, in
            # ``overlay/dropdown/theme.py``.
            "transition-opacity duration-75 "
            "starting:opacity-0"
        ),
    },
    # ── Size steps ───────────────────────────────────────────────
    # The height lives on ``input_frame``, NOT on ``input_field`` — and
    # it is load-bearing. The frame carries the border; under
    # ``box-sizing: border-box`` (Tailwind's preset), an ``h-10`` set on
    # the frame is 40 px border included, exactly like ``ui.input``,
    # which sets its height and its border on the SAME element. Set on
    # the child, it would give 40 px + the frame's 2 px, that is 2 px more
    # than any other control, at each of the five steps. Guarded by
    # ``tests/runtime_js/test_form_controls_share_one_height.py``.
    #
    # The children therefore have no ``h-*``: the frame is
    # ``items-stretch``, they fill its inner height. Giving them one
    # would make them overflow the frame.
    "sizes": {
        # One row per step, one entry per slot — the shape of every
        # other table (``sizes[<size>][<slot>]``). The base composer puts
        # a row's entry on the slot of that name, for every component.
        "xs": {
            "input_frame": "h-7",
            "input_field": "text-xs",
            "clear_button": "w-6",
            "trigger_button": "w-7",
            "button_icon": "text-xs",
        },
        "sm": {
            "input_frame": "h-8",
            "input_field": "text-sm",
            "clear_button": "w-7",
            "trigger_button": "w-8",
            "button_icon": "text-sm",
        },
        "md": {
            "input_frame": "h-10",
            "input_field": "text-sm",
            "clear_button": "w-8",
            "trigger_button": "w-10",
            "button_icon": "text-base",
        },
        "lg": {
            "input_frame": "h-12",
            "input_field": "text-base",
            "clear_button": "w-9",
            "trigger_button": "w-12",
            "button_icon": "text-lg",
        },
        "xl": {
            "input_frame": "h-14",
            "input_field": "text-lg",
            "clear_button": "w-10",
            "trigger_button": "w-14",
            "button_icon": "text-xl",
        },
    },
}
