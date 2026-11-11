"""Default :class:`Stat` theme.

A surface like ``ui.card``'s — its hairline, its radius, its padding
scale read from the same ``--bz-pad-*`` steps, so an app that tightens
its cards tightens its key figures with them. The classes are written
here, not shared: they are harmonised, not factored.

Slots :
- ``root``        : the surface, a column
- ``label``       : what the number is
- ``value_row``   : the number and its change, side by side
- ``value``       : the number
- ``meter``       : the track of the gauge (``role="meter"``)
- ``fill``        : the part of the range the value covers
- ``target``      : the objective's mark across the track
- ``scale``       : under the track — the objective (or 0), the maximum
- ``toned``       : a text in the objective's colour (reached or not)
- ``status``      : the objective said in a line, when there is no range
- ``description`` : a line under it all
"""

from __future__ import annotations

from typing import Any

STAT_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "flex flex-col gap-1 w-full min-w-0 rounded-box bg-surface text-text "
            "border-(length:--bz-stroke) border-text/10 "
            "p-(--bz-pad-4) sm:p-(--bz-pad-6)"
        ),
        "label": "text-sm text-muted",
        "value_row": "flex flex-wrap items-center gap-2",
        # One line, never split inside « 48 240 € »; in a cell narrower
        # than the number it ends in « … » (its ``title`` says it whole)
        # instead of spilling out of the surface.
        "value": "min-w-0 max-w-full truncate text-2xl font-semibold leading-tight tabular-nums",
        # The mark overflows the track by design (``-top-1 -bottom-1``):
        # no ``overflow-hidden`` here, the fill is rounded on its own.
        "meter": "relative h-2 mt-1 rounded-full bg-text/10",
        "fill": "h-full rounded-full bg-(--bz-solid)",
        "target": "absolute -top-1 -bottom-1 w-0.5 -ml-px rounded-full bg-text",
        "scale": "flex justify-between gap-2 text-xs tabular-nums text-muted",
        "toned": "text-(--bz-text)",
        "status": "text-sm text-(--bz-text)",
        "description": "text-sm text-muted",
    },
}
