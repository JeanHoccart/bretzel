"""Default :class:`Textarea` theme.

Same identity as Input — soft border, generous radius, focus ring
tinted to the colour. ``resize-none`` keeps the visual stable (the
``rows`` prop drives initial height ; ``autosize`` will grow it via
JS once we wire that ; manual user resize is opt-in via
``classes="resize-y"`` or similar override).
"""

from __future__ import annotations

from typing import Any

TEXTAREA_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-textarea "  # audit marker — cf. tests/audit/checklist.py
            # The frame and its focus ring are the variant's (``variants``).
            "block w-full rounded-field "
            "text-text placeholder:text-placeholder "
            "outline-none resize-none transition duration-200 "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "read-only:cursor-default"
        ),
    },
    "variants": {
        "surface": "bg-interface border-(length:--bz-stroke) border-line focus:border-(--bz-solid) focus:ring-2 focus:ring-(--bz-focus-soft) focus:ring-offset-2 focus:ring-offset-background disabled:bg-tint read-only:bg-tint",
        "ghost": "[[data-bz-keyboard]_&]:focus:ring-2 [[data-bz-keyboard]_&]:focus:ring-(--bz-focus) [[data-bz-keyboard]_&]:focus:ring-offset-2 [[data-bz-keyboard]_&]:focus:ring-offset-background",
    },
    "sizes": {
        "xs": "px-2 py-1 text-xs",
        "sm": "px-3 py-1.5 text-sm",
        "md": "px-3 py-2 text-sm",
        "lg": "px-4 py-2.5 text-base",
        "xl": "px-5 py-3 text-lg",
    },
}
