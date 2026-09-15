"""Default themes for :class:`RadioGroup` and :class:`Radio`.

Same idiom as the checkbox / switch — ``peer sr-only`` real
``<input type="radio">`` + a fake ``<div class="circle">`` + an
absolute-positioned ``<div class="dot">`` that fades in on
``peer-checked``. Each radio shares the ``name=`` from the parent
RadioGroup so the browser groups them as one single-choice cluster.
"""

from __future__ import annotations

from typing import Any

RADIO_GROUP_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex gap-4",
    },
    "directions": {
        "col": "flex-col",
        "row": "flex-row flex-wrap",
    },
}

RADIO_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "inline-flex items-center gap-2 group select-none cursor-pointer "
            # Disabled visual — fully CSS-reactive via the hidden peer
            # ``<input disabled>`` descendant. Same shape as Checkbox /
            # Switch so the family stays uniform.
            "has-[:disabled]:opacity-50 "
            "has-[:disabled]:cursor-not-allowed"
        ),
        "container": (
            "relative inline-flex items-center justify-center shrink-0"
        ),
        "input": "peer sr-only",
        "circle": (
            "block rounded-full border-(length:--bz-stroke) border-text/10 bg-interface "
            "transition-all duration-200 ease-out "
            "peer-checked:border-(--bz-solid) peer-checked:border-(length:--bz-stroke-strong) "
            "peer-focus-visible:ring-2 peer-focus-visible:ring-(--bz-focus) "
            "peer-focus-visible:ring-offset-2 "
            "peer-focus-visible:ring-offset-background"
        ),
        "dot": (
            # Center on the ``container`` (its nearest ``relative``
            # ancestor) via the textbook ``top-1/2 left-1/2 -translate``
            # pattern. Without explicit anchors, ``absolute`` falls
            # back to the element's static flex position — which
            # places the dot AFTER the circle instead of ON it.
            "absolute top-1/2 left-1/2 "
            "-translate-x-1/2 -translate-y-1/2 "
            "pointer-events-none rounded-full "
            "bg-(--bz-solid) opacity-0 peer-checked:opacity-100 "
            "transition-opacity duration-200 ease-out"
        ),
        "label": (
            "font-medium text-text transition-all duration-200 "
            "group-has-[input:not(:disabled)]:group-hover:opacity-70"
        ),
    },
    # Per-size dict : circle, dot, label all scale together so the
    # visual proportions stay tight.
    "sizes": {
        "xs": {"circle": "h-3 w-3", "dot": "h-1.5 w-1.5", "label": "text-[10px]"},
        "sm": {"circle": "h-4 w-4", "dot": "h-2 w-2",     "label": "text-xs"},
        "md": {"circle": "h-5 w-5", "dot": "h-2.5 w-2.5", "label": "text-sm"},
        "lg": {"circle": "h-6 w-6", "dot": "h-3 w-3",     "label": "text-base"},
        "xl": {"circle": "h-7 w-7", "dot": "h-3.5 w-3.5", "label": "text-lg"},
    },
}
