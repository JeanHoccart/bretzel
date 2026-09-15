"""Default :class:`NumberInput` theme.

Numeric input with vertical ± stepper buttons stacked on the right.
Visual identity tracks Input / Select so a form mixing the three
reads as a single family.

Slots :
- ``root``     : outer wrapper that hosts the bordered shell
- ``shell``    : the bordered + focus-ring container
- ``input``    : the actual ``<input type="text">``
                 (we use type="text" + inputmode="decimal" so the
                 browser shows the numeric keyboard on mobile but
                 we keep full control over parsing / step / clamp)
- ``steppers`` : vertical column holding the ▲ / ▼ buttons
- ``stepper`` : individual stepper button (▲ or ▼)
- ``chevron`` : the icon inside a stepper button
"""

from __future__ import annotations

from typing import Any

NUMBER_INPUT_THEME: dict[str, Any] = {
    "slots": {
        "root": "bz-number-input relative w-full",
        # Bordered shell — same recipe as Input / Select for
        # visual consistency. ``focus-within`` so the ring fires
        # when the inner input is focused (we don't focus the
        # shell itself).
        "shell": (
            "flex items-stretch w-full rounded-field border-(length:--bz-stroke) "
            "border-text/10 bg-interface text-text "
            "transition-all duration-200 "
            "focus-within:border-(--bz-solid) "
            "focus-within:ring-2 focus-within:ring-(--bz-focus-soft) "
            "focus-within:ring-offset-2 "
            "focus-within:ring-offset-background "
            "has-[input:disabled]:opacity-50 "
            "has-[input:disabled]:cursor-not-allowed "
            "has-[input:disabled]:bg-muted/10 "
            "overflow-hidden"
        ),
        # The text input — flex-1, borderless because the shell
        # carries the border. ``tabular-nums`` so digit widths
        # stay stable (no jiggle as the user types).
        "input": (
            "flex-1 min-w-0 bg-transparent outline-none "
            "border-none p-0 text-text tabular-nums "
            "placeholder:text-muted/70 "
            "disabled:cursor-not-allowed"
        ),
        # Vertical stack of ▲ / ▼ — fixed width, left border to
        # separate from the input visually. ``divide-y`` puts a
        # 1px line between the two buttons.
        "steppers": (
            "flex flex-col shrink-0 border-l-(length:--bz-stroke) border-text/10 "
            "divide-y divide-text/10"
        ),
        # One stepper button. Compact (half the input height each)
        # so they stack to match the input. ``cursor-pointer`` +
        # hover bg for affordance.
        "stepper": (
            "flex items-center justify-center "
            "flex-1 px-2 "
            "text-muted not-disabled:hover:text-(--bz-text) "
            "not-disabled:hover:bg-(--bz-bg) "
            "cursor-pointer outline-none "
            "transition-colors duration-100 "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
        # Chevron sizing handled by the size scale below ; this
        # slot is just the layout for the icon.
        "chevron": "shrink-0",
    },
    # Sizes mirror Input — same heights so a NumberInput sitting
    # next to an Input lines up perfectly.
    "sizes": {
        "xs": {"shell": "h-7", "input": "px-2 text-xs"},
        "sm": {"shell": "h-8", "input": "px-3 text-xs"},
        "md": {"shell": "h-10", "input": "px-3 text-sm"},
        "lg": {"shell": "h-12", "input": "px-4 text-base"},
        "xl": {"shell": "h-14", "input": "px-5 text-lg"},
    },
}
