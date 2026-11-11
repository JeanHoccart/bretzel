"""Default :class:`DateRangePicker` theme.

Same layout idea as :data:`DATE_PICKER_THEME` — one focus-within
frame around the two editable inputs, the separator, and the single
shared calendar icon button.
"""

from __future__ import annotations

from typing import Any

DATE_RANGE_PICKER_THEME: dict[str, Any] = {
    "slots": {
        # ``w-full`` (not ``w-fit``) : fills its parent like every other form
        # input, so it aligns with siblings in a grid / form_field and doesn't
        # grow past a constrained cell (same fix as date_picker). Paired with
        # the ``flex-1 min-w-0`` inputs below, the whole field shrinks to fit
        # any cell instead of overflowing.
        "root": (
            "bz-date-range-picker relative flex flex-col w-full"
        ),
        # The unified field — both inputs + separator + buttons sit
        # under one ring.
        "input_frame": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text transition duration-200 "
            "focus-within:border-(--bz-solid) focus-within:ring-2 "
            "focus-within:ring-(--bz-focus-soft) focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed"
        ),
        # Each editable date input — ``flex-1 min-w-0`` (NOT a fixed
        # ``w-[8.5rem]``) so the two fields SHARE the frame and shrink with
        # it, same as date_picker's input. A fixed width gave the frame a
        # ~2×8.5rem + separator + button min-content floor : in a cell
        # narrower than that the content overflowed the frame internally
        # (clipped / scrolled) even after the root was capped to the cell.
        # ``h-*`` / ``text-*`` moved to sizes map below so ``size=`` propagates.
        "input_field": (
            "flex-1 min-w-0 px-3 bg-transparent text-text tabular-nums "
            "placeholder:text-muted/60 outline-none "
            "disabled:cursor-not-allowed"
        ),
        # Tight padding-only on the start field so the separator sits
        # snug.
        "input_field_start": (
            "rounded-l-field"
        ),
        # Separator chip between the two inputs.
        "separator": (
            "inline-flex items-center text-text/50 px-1 "
            "select-none"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center "
            "text-muted/60 not-disabled:hover:text-text outline-none "
            "transition-colors disabled:opacity-50 "
            "disabled:cursor-not-allowed"
        ),
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
        "button_icon": (
            "inline-flex shrink-0 text-current"
        ),
        # Positioned by ``$bz.helpers.floating`` (fixed + inline top/left,
        # flip / clamp) — no static ``top-full left-0`` (those fight the inline
        # coords under fixed). Same as date_picker / Select / Combobox.
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
            "separator": "text-xs",
            "clear_button": "w-6",
            "trigger_button": "w-7",
            "button_icon": "text-xs",
        },
        "sm": {
            "input_frame": "h-8",
            "input_field": "text-sm",
            "separator": "text-sm",
            "clear_button": "w-7",
            "trigger_button": "w-8",
            "button_icon": "text-sm",
        },
        "md": {
            "input_frame": "h-10",
            "input_field": "text-sm",
            "separator": "text-sm",
            "clear_button": "w-8",
            "trigger_button": "w-10",
            "button_icon": "text-base",
        },
        "lg": {
            "input_frame": "h-12",
            "input_field": "text-base",
            "separator": "text-base",
            "clear_button": "w-9",
            "trigger_button": "w-12",
            "button_icon": "text-lg",
        },
        "xl": {
            "input_frame": "h-14",
            "input_field": "text-lg",
            "separator": "text-lg",
            "clear_button": "w-10",
            "trigger_button": "w-14",
            "button_icon": "text-xl",
        },
    },
}
