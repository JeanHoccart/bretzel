"""``Reference`` dataclass — horizontal threshold line + label.

A reference line is a horizontal rule rendered behind the data,
usually annotating a goal, a release marker, a baseline, or a
threshold. The label sits at the right edge of the plot area so it
doesn't compete with the data.

API ::

    ui.line_chart(
        revenue,
        reference_lines=[
            Reference(value=1000, label="Q3 target"),
            Reference(value=2000, label="Stretch", color="success"),
        ],
    )

A bare tuple ``(value, label)`` is also accepted ; ``(value, label,
color)`` lets the app pin the colour. ``color=None`` falls back to
``"muted"`` so the reference doesn't compete with the series'
palette colours.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Reference:
    """One reference line on a chart's y axis."""

    value: float
    label: str = ""
    color: str | None = None
