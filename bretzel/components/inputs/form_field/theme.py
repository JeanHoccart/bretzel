"""Default :class:`FormField` theme.

Vertical stack of ``label → input(s) → hint or error``. Label and
hint stay subdued ; error swings to ``text-error`` so the user can't
miss it.
"""

from __future__ import annotations

from typing import Any

FORM_FIELD_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-1.5 w-full",
        "label": "text-sm font-medium text-text",
        "label_required": "text-error ml-0.5",  # the "*" suffix
        "hint": "text-xs text-muted",
        "error": "text-xs text-error font-medium",
    },
}
