"""Default :class:`Container` theme.

A centered max-width column with baked horizontal + vertical padding.
The width clamp is selectable via ``width=`` ; ``full`` opts out of the
clamp entirely (no ``max-w-*`` class is appended). Padding is baked
into the root slot and intentionally not exposed as a prop — apps that
need a different spacing scale compose ``Container > VStack`` with a
custom ``gap``, or pass the rare-atypical ``classes=`` override.
"""

from __future__ import annotations

from typing import Any

CONTAINER_THEME: dict[str, Any] = {
    "slots": {
        # ``mx-auto`` centers, ``w-full`` lets the max-width clamp it,
        # ``py-8`` and the horizontal margin are the baked content
        # padding. The horizontal margin is the box family's
        # ``--bz-pad-6`` (1.5rem by default): it is the
        # one ``ui.navbar(width=…)`` writes too, so a bar and a page of
        # the same width share their left edge whatever the theme's
        # ``spacing=`` says. Gated by ``test_a_bar_lines_up_with_its_page``.
        "root": "mx-auto w-full px-(--bz-pad-6) py-8",
    },
    "widths": {
        "sm":   "max-w-2xl",
        "md":   "max-w-3xl",
        "lg":   "max-w-5xl",
        "xl":   "max-w-7xl",
        "2xl":  "max-w-screen-2xl",
        "full": "",
    },
}
