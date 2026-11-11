"""The histogram: raw values counted per tranche, drawn by the bar chart.

Its own package and not a ``variant`` of ``bar_chart``: it takes values,
not pairs, and owns the tranches — their bounds, the mean, a click that
says the tranche.
"""

from __future__ import annotations

from bretzel.components.charts.histogram.histogram import Histogram

__all__ = ["Histogram"]
