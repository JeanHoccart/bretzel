"""Default :class:`Progress` theme.

A simple two-layer bar : an outer rounded track tinted at 10% of the
color, an inner fill that grows by setting ``width: <value>%``. The
indeterminate mode replaces the static fill with an animated stripe
(``animate-pulse`` is the closest Tailwind built-in ; for a sliding-
gradient look use ``classes="…"`` to override).

Slots :
- ``root`` : full-width relative wrapper (also where ``role`` lives)
- ``track``: the background bar
- ``fill`` : the colored bar that grows
- ``label``: optional inline percentage text on the right
"""

from __future__ import annotations

from typing import Any

PROGRESS_THEME: dict[str, Any] = {
    "slots": {
        "root": "w-full flex items-center gap-2",
        "track": (
            "relative flex-1 overflow-hidden rounded-full "
            "bg-(--bz-bg)"
        ),
        # Inner fill : ``transition-[width]`` so updates animate cleanly.
        "fill": (
            "h-full rounded-full bg-(--bz-solid) "
            "transition-[width] duration-300 ease-out"
        ),
        # Indeterminate fill : pulse + opacity shift so it doesn't sit
        # dead on screen.
        "fill_indeterminate": (
            "absolute inset-0 rounded-full bg-(--bz-solid) "
            "animate-pulse opacity-70"
        ),
        "label": "text-xs text-text/70 tabular-nums shrink-0",
    },
    # Track height per size — the fill follows the track via ``h-full``.
    "sizes": {
        "xs": "h-1",
        "sm": "h-1.5",
        "md": "h-2",
        "lg": "h-3",
        "xl": "h-4",
    },
}
