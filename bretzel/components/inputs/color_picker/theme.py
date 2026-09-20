"""Default :class:`ColorPicker` theme.

The picker family's silhouette — a bordered frame carrying the step's
height, an editable field inside, a trigger button on the right, an
anchored panel. The only difference is the panel's content: a grid of
swatches instead of a grid of days.

⚠️ **The step's height is on the FRAME**, which carries the border.
Setting it on the inner ``<input>`` renders 2 px more (``box-sizing:
border-box`` counts the border), and the gap only shows on screen — cf.
``traps.md`` § *A step's height on the CHILD*.

The head swatch is not decorative: it is the only place where the value
reads **as a colour**. A hexadecimal does not read back.
"""

from __future__ import annotations

from typing import Any

COLOR_PICKER_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-color-picker relative flex flex-col w-full",
        "input_frame": (
            "flex items-center gap-2 w-full rounded-field border-(length:--bz-stroke) "
            "border-text/15 bg-interface transition-colors "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 focus-within:ring-offset-background "
            "has-[:disabled]:opacity-50 has-[:disabled]:cursor-not-allowed"
        ),
        # The head swatch — it RENDERS the current value.
        #
        # ⚠️ ``bg-text/5`` and not a checkerboard: the first writing was a
        # ``repeating-conic-gradient`` split into TWO Python literals to
        # fit on the line, and the Tailwind compiler scans the sources —
        # it would have seen neither half. A class non-existent in prod,
        # a correct checkerboard in dev. Caught by
        # ``test_emitted_classes_exist_in_source`` before it shipped.
        #
        # The resting grey plays the same role: a swatch WITH NO colour
        # is not confused with a white swatch.
        "swatch": (
            "shrink-0 rounded-selector border-(length:--bz-stroke) border-text/15 bg-text/5"
        ),
        "input_field": (
            "flex-1 min-w-0 bg-transparent outline-none font-mono "
            "text-text placeholder:text-muted/70 "
            "disabled:cursor-not-allowed"
        ),
        "clear_button": (
            "shrink-0 inline-flex items-center justify-center rounded-selector "
            "text-muted hover:text-text transition-colors cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:cursor-not-allowed"
        ),
        "trigger_button": (
            "shrink-0 inline-flex items-center justify-center rounded-selector "
            "text-muted hover:text-text transition-colors cursor-pointer "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "disabled:cursor-not-allowed"
        ),
        "button_icon": "",
        "panel": (
            "absolute z-50 mt-1 rounded-box border-(length:--bz-stroke) border-text/10 "
            "bg-surface shadow-lg p-3 w-max max-w-[min(20rem,100vw-2rem)] "
            # The enter fade, FIELD cadence (75 ms, half the menus').
            # Mechanism of the three classes: a single copy, in
            # ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-75 "
            "starting:opacity-0"
        ),
        "grid": "grid grid-cols-8 gap-1.5",
        # One swatch of the panel. ``data-selected`` marks the one that
        # equals the current value — the ring designates it without
        # changing its size, so the grid does not move when the selection
        # changes.
        "swatch_cell": (
            "h-6 w-6 rounded-selector border-(length:--bz-stroke) border-text/15 cursor-pointer "
            "transition-transform hover:scale-110 "
            "outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) focus-visible:ring-offset-1 "
            "focus-visible:ring-offset-surface "
            "data-[selected=true]:ring-2 "
            "data-[selected=true]:ring-(--bz-solid) "
            "data-[selected=true]:ring-offset-2 "
            "data-[selected=true]:ring-offset-surface"
        ),
        "panel_label": "text-xs text-muted mb-2 font-medium",
    },
    # ``sizes[<step>][<slot>]`` — the CANONICAL shape. The three date
    # pickers write it inverted and are declared exceptions; a new
    # component has no reason to imitate them there.
    #
    # The scale is the controls' — ``h-7/h-8/h-10/h-12/h-14``, the same
    # as Input's and Select's. A missing step does not raise: the render
    # falls back on ``md``, so the field comes out smaller than its
    # neighbour at the same step, and that only shows on screen.
    "sizes": {
        "xs": {
            "input_frame": "h-7 px-1.5", "swatch": "h-4 w-4",
            "input_field": "text-xs", "clear_button": "h-4 w-4",
            "trigger_button": "h-4 w-4", "button_icon": "xs",
        },
        "sm": {
            "input_frame": "h-8 px-2", "swatch": "h-5 w-5",
            "input_field": "text-xs", "clear_button": "h-5 w-5",
            "trigger_button": "h-5 w-5", "button_icon": "sm",
        },
        "md": {
            "input_frame": "h-10 px-2.5", "swatch": "h-6 w-6",
            "input_field": "text-sm", "clear_button": "h-6 w-6",
            "trigger_button": "h-6 w-6", "button_icon": "md",
        },
        "lg": {
            "input_frame": "h-12 px-3", "swatch": "h-7 w-7",
            "input_field": "text-base", "clear_button": "h-7 w-7",
            "trigger_button": "h-7 w-7", "button_icon": "md",
        },
        "xl": {
            "input_frame": "h-14 px-3.5", "swatch": "h-8 w-8",
            "input_field": "text-lg", "clear_button": "h-8 w-8",
            "trigger_button": "h-8 w-8", "button_icon": "lg",
        },
    },
}
