"""Default :class:`Text` theme.

A separate file so an aggregator can import the dict without dragging the
component class. No such aggregator exists today, and the reason is worth
keeping : the shipped scale is a DEFAULT (``DEFAULT_SPACING`` /
``DEFAULT_TEXT`` in ``bretzel/theme/tokens.py``), not a preset. A preset
package was tried on 2026-09-13 and removed the same day — one that
matches the default is a trap, and one that differs is a second way to say
the same thing. Component code MUST NOT
import this dict directly — it should always read merged values
through ``self._resolved_theme()`` (which deep-merges the user's
``Theme(components=…)`` override onto ``cls.THEME``, memoized) so
user-side overrides are honoured.
"""

from __future__ import annotations

from typing import Any

TEXT_THEME: dict[str, Any] = {
    "slots": {
        "root": "leading-normal",
    },
    "sizes": {
        "xs": "text-xs",
        "sm": "text-sm",
        "md": "text-base",
        "lg": "text-lg",
        "xl": "text-xl",
        "2xl": "text-2xl",
        "3xl": "text-3xl",
        "4xl": "text-4xl",
        "5xl": "text-5xl",
        "6xl": "text-6xl",
    },
    "weights": {
        "normal": "font-normal",
        "medium": "font-medium",
        "semibold": "font-semibold",
        "bold": "font-bold",
    },
    "alignments": {
        "left": "text-left",
        "center": "text-center",
        "right": "text-right",
        "justify": "text-justify",
    },
    "decorations": {
        "none": "no-underline",
        "underline": "underline",
        "line-through": "line-through",
    },
    "modifiers": {
        "italic": "italic",
        "truncate": "truncate",
        "color": "text-(--bz-text)",
    },
}
