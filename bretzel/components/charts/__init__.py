"""Tier 8 — data visualisation.

Server-rendered SVG charts. No external JS library is loaded — hover
tooltips and legend toggles ride ``$bz.charts.*`` scope factories
declared via ``bz-data`` on the chart wrapper. These are LIVE : the
runtime slab ``bretzel/runtime/_src/10_charts.js`` ships
``tooltipScope`` / ``lineScope`` / ``scatterScope`` and the chart
components wire them (``bz-data="$bz.charts.tooltipScope()"`` +
per-mark ``bz-on:mouseenter``).

Public surface :

- :class:`Sparkline`    — inline trend indicator (single series, no axes).
- :class:`BarChart`     — categorical bars, single or multi-series.
- :class:`LineChart`    — continuous line, single or multi-series.
- :class:`PieChart`     — pie / donut.
- :class:`ScatterChart` — continuous X/Y dots, independent series.
- :class:`Series`       — light dataclass for multi-series payloads.
- :class:`Reference`    — horizontal threshold line annotation.

Optimised for 10 – 1 000 points per chart. Beyond that range, SVG
becomes the bottleneck (one DOM node per point) ; a Canvas-backed
variant (uPlot or similar) would land as a separate component family
when a concrete need arrives.
"""

from __future__ import annotations

from bretzel.components.charts.bar_chart import BarChart
from bretzel.components.charts.line_chart import LineChart
from bretzel.components.charts.pie_chart import PieChart
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.scatter_chart import ScatterChart
from bretzel.components.charts.series import Series
from bretzel.components.charts.sparkline import Sparkline

__all__ = [
    "BarChart", "LineChart", "PieChart",
    "Reference", "ScatterChart", "Series", "Sparkline",
]
