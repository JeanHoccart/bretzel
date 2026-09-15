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
            "block w-full rounded-field border-(length:--bz-stroke) border-text/10 "
            "bg-interface text-text placeholder:text-muted/60 "
            "outline-none resize-none transition-all duration-200 "
            "focus:border-(--bz-solid) "
            "focus:ring-2 focus:ring-(--bz-focus-soft) "
            "focus:ring-offset-2 focus:ring-offset-background "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "disabled:bg-muted/10 "
            "read-only:cursor-default read-only:bg-interface/50"
        ),
    },
    "sizes": {
        "xs": "px-2 py-1 text-xs",
        "sm": "px-3 py-1.5 text-xs",
        "md": "px-3 py-2 text-sm",
        "lg": "px-4 py-2.5 text-base",
        "xl": "px-5 py-3 text-lg",
    },
}
