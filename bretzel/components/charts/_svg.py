"""Shared SVG primitives for the chart components.

Pure functions, with ONE exception, and it is named here because the
docstring lied for the length of a commit: :func:`format_value` reads
``text("chart.currency")`` for the currency symbol, so it consults the
render context. Everything else builds no ``Element`` and imports
nothing from the framework — each chart composes its ``<svg>`` by
calling these helpers and assembling the tree itself.

The exception stays testable in isolation: outside a context,
:func:`~bretzel.render.texts.text` falls back on the English table, so a
bare call returns what it returned before. What was weighed and ruled
out: passing the symbol from the calling component (which has the
context) would have added a parameter to seven sites to preserve a
purity only this file claims.

Conventions :

- Coordinates use the SVG convention : ``(0, 0)`` is the top-left,
  ``y`` grows downward. Helpers that take a "domain" (data space) flip
  the axis as needed.
- All numeric output is rounded to **2 decimals**. SVG accepts more,
  but the byte-saving on long paths is meaningful (10–30 %) and
  visually indistinguishable.
- Empty inputs (``[]``) return safe sentinels (``""`` for paths, the
  domain endpoints unchanged) — callers decide how to render the empty
  state.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

from bretzel.render import text

# ───────────────────────────────────────────────────────────────────────
# Value formatting
# ───────────────────────────────────────────────────────────────────────


def format_value(
    value: float,
    fmt: str | Callable[[float], str] | None,
    unit: str | None = None,
) -> str:
    """Format a numeric value for axis ticks, bar labels, tooltips.

    ``fmt`` accepts a callable (full control) or one of three shorthand
    strings :

    - ``"abbreviated"`` — ``1 234`` → ``"1.2k"``, ``2_500_000`` → ``"2.5M"``.
      Sweet spot for KPI charts where the magnitude matters more than the
      decimals.
    - ``"percent"``    — ``0.42`` → ``"42%"`` (multiplies by 100).
    - ``"currency"``   — ``1234.5`` → ``"$1,234.50"``. The symbol and its
      place come from the ``chart.currency`` text key, so an app writes
      ``texts={"chart.currency": "{value} €"}`` once and for all. The
      thousands separator stays English: it is a number-formatting axis,
      not a framework word.

    ``None`` falls back to terse ``"1234"`` (int-like) or ``"3.14"``
    (with decimals, trailing zeros stripped).

    ``unit`` (optional) appends a space-separated suffix —
    ``unit="ms"`` → ``"91 ms"``, ``unit="users"`` → ``"1.2k users"``.
    Skipped silently when ``fmt`` is a callable (the caller owns the
    full output) and when ``fmt="percent"`` (the ``%`` is already the
    unit). For ``fmt="currency"`` the suffix appends after the dollar
    amount — useful for cross-currency contexts where ``$ ... USD``
    avoids ambiguity.
    """
    if callable(fmt):
        return str(fmt(value))
    if fmt == "abbreviated":
        absv = abs(value)
        if absv >= 1_000_000_000:
            base = f"{value / 1_000_000_000:.1f}B".replace(".0B", "B")
        elif absv >= 1_000_000:
            base = f"{value / 1_000_000:.1f}M".replace(".0M", "M")
        elif absv >= 1_000:
            base = f"{value / 1_000:.1f}k".replace(".0k", "k")
        else:
            base = _plain(value)
    elif fmt == "percent":
        return f"{round(value * 100)}%"
    elif fmt == "currency":
        base = text("chart.currency", value=f"{value:,.2f}")
    else:
        base = _plain(value)
    return f"{base} {unit}" if unit else base


def _plain(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def linear_scale(
    domain_min: float,
    domain_max: float,
    range_min: float,
    range_max: float,
) -> Callable[[float], float]:
    """Return a function mapping ``domain_*`` linearly into ``range_*``.

    Degenerate domain (``domain_min == domain_max``) collapses to the
    midpoint of the range — avoids a divide-by-zero and renders a flat
    line / centred bar, which is the only sensible visual for a
    constant series.
    """
    span = domain_max - domain_min
    if span == 0:
        midpoint = (range_min + range_max) / 2

        def _flat(_: float) -> float:
            return midpoint

        return _flat

    factor = (range_max - range_min) / span

    def _scale(value: float) -> float:
        return range_min + (value - domain_min) * factor

    return _scale


def nice_domain(values: Iterable[float], pad_ratio: float = 0.05) -> tuple[float, float]:
    """Pick a (min, max) that frames ``values`` with a small visual pad.

    - Empty input → ``(0.0, 1.0)`` (neutral default).
    - Single value → ``(v - 1, v + 1)`` to avoid a zero span.
    - Otherwise pad by ``pad_ratio`` of the span on each side, but never
      cross zero if the original data didn't (keeps bar charts anchored
      to the axis instead of floating above a negative-padded base).
    """
    seq = list(values)
    if not seq:
        return (0.0, 1.0)
    lo = min(seq)
    hi = max(seq)
    if lo == hi:
        return (lo - 1.0, hi + 1.0)
    span = hi - lo
    pad = span * pad_ratio
    new_lo = lo - pad
    new_hi = hi + pad
    if lo >= 0 and new_lo < 0:
        new_lo = 0.0
    if hi <= 0 and new_hi > 0:
        new_hi = 0.0
    return (new_lo, new_hi)


def _nice_number(rough: float, round_to_one_of: bool) -> float:
    """Round ``rough`` to a "nice" number — 1, 2, 5 or 10 times a power of 10."""
    if rough == 0:
        return 0
    exponent = math.floor(math.log10(abs(rough)))
    fraction = abs(rough) / (10**exponent)
    if round_to_one_of:
        if fraction < 1.5:
            nice = 1
        elif fraction < 3:
            nice = 2
        elif fraction < 7:
            nice = 5
        else:
            nice = 10
    else:
        if fraction <= 1:
            nice = 1
        elif fraction <= 2:
            nice = 2
        elif fraction <= 5:
            nice = 5
        else:
            nice = 10
    return math.copysign(nice * (10**exponent), rough)


def compute_ticks(
    domain_min: float,
    domain_max: float,
    target_count: int = 5,
) -> list[float]:
    """Return ``target_count``-ish "nice" tick values BRACKETING the
    domain. The first and last ticks fall on round numbers that extend
    *past* ``domain_min`` / ``domain_max`` — callers typically use
    these endpoints as the chart's visible y-range so the axis line
    spans full ticks and the visual bottom isn't a half-step above the
    smallest data point (which created the "gridline starts at 60 even
    though data goes down to 45" surprise).

    Uses the Heckbert nice-numbers algorithm — same routine D3 ships
    in ``d3-scale``. Output count is approximate (``target_count ± 2``).
    """
    if domain_min == domain_max or target_count < 2:
        return [domain_min] if domain_min == domain_max else [domain_min, domain_max]
    span = _nice_number(domain_max - domain_min, round_to_one_of=False)
    step = _nice_number(span / (target_count - 1), round_to_one_of=True)
    start = math.floor(domain_min / step) * step
    end = math.ceil(domain_max / step) * step
    ticks: list[float] = []
    value = start
    # Tolerance avoids float drift dropping the last tick.
    while value <= end + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _fmt(n: float) -> str:
    """Round to 2 decimals and strip trailing zeros for terse SVG output."""
    return f"{round(n, 2):g}"


def line_path(points: list[tuple[float, float]]) -> str:
    """SVG ``d`` attribute for a polyline through ``points``.

    Returns ``""`` for empty input (caller decides whether to render
    nothing or an empty-state placeholder).
    """
    if not points:
        return ""
    out = [f"M{_fmt(points[0][0])},{_fmt(points[0][1])}"]
    for x, y in points[1:]:
        out.append(f"L{_fmt(x)},{_fmt(y)}")
    return "".join(out)


def smooth_path(points: list[tuple[float, float]]) -> str:
    """SVG ``d`` for a Catmull-Rom-as-Bézier curve through ``points``.

    Same visual algorithm D3 uses for ``curveCatmullRom``. The smooth
    line passes through every given point ; the tangents are derived
    from the neighbours, which gives a natural-feeling curve without
    the overshoot you get from a pure cubic spline. Degenerate cases
    (<2 points) fall back to a straight path.
    """
    n = len(points)
    if n < 2:
        return line_path(points)
    if n == 2:
        return line_path(points)
    out = [f"M{_fmt(points[0][0])},{_fmt(points[0][1])}"]
    # Reflect the first / last point for the boundary cases — same
    # trick as ``d3-shape``'s Catmull-Rom implementation.
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        # Catmull-Rom tension = 0.5 (the centripetal default).
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        out.append(
            f"C{_fmt(c1x)},{_fmt(c1y)} {_fmt(c2x)},{_fmt(c2y)} "
            f"{_fmt(p2[0])},{_fmt(p2[1])}"
        )
    return "".join(out)


def area_path(
    points: list[tuple[float, float]],
    *,
    baseline_y: float,
    smooth: bool = False,
) -> str:
    """Closed path filling the region between ``points`` and ``baseline_y``.

    Useful for sparkline / line-chart area fills. The path starts at
    the first point, traces through the data, drops to the baseline at
    the last x, walks back to the first x along the baseline, then
    closes — yielding a filled silhouette.
    """
    if not points:
        return ""
    upper = smooth_path(points) if smooth else line_path(points)
    first_x = _fmt(points[0][0])
    last_x = _fmt(points[-1][0])
    baseline = _fmt(baseline_y)
    return f"{upper}L{last_x},{baseline}L{first_x},{baseline}Z"


def arc_path(
    cx: float,
    cy: float,
    radius: float,
    start_rad: float,
    end_rad: float,
    inner_radius: float = 0.0,
) -> str:
    """SVG path for a pie wedge (``inner_radius=0``) or donut wedge.

    Angles are in radians, measured clockwise from the **top** of the
    circle (i.e. 0 rad = 12 o'clock, π/2 = 3 o'clock). This matches the
    convention users expect when reading pie charts.
    """
    if end_rad - start_rad <= 0:
        return ""
    # SVG arcs can't draw a full 360° in a single A command.
    if end_rad - start_rad >= 2 * math.pi - 1e-9:
        if inner_radius <= 0:
            # Solid pie / single 100% slice — render as a closed circle
            # (two back-to-back semicircle arcs) so the path has no
            # ``L``-to-centre cuts. The previous "split into two
            # wedges and concatenate" approach overlapped the centre-
            # to-edge segments and showed a vertical seam through the
            # middle when stroked between slices.
            r = _fmt(radius)
            return (
                f"M{_fmt(cx - radius)},{_fmt(cy)} "
                f"A{r},{r} 0 1 1 {_fmt(cx + radius)},{_fmt(cy)} "
                f"A{r},{r} 0 1 1 {_fmt(cx - radius)},{_fmt(cy)} Z"
            )
        # Full donut — keep the split-and-merge ; the two halves share
        # a radial seam from inner to outer, which is the visual
        # contract for "donut where every slice belongs to the same
        # category" (rare in practice).
        mid = start_rad + math.pi
        return (
            arc_path(cx, cy, radius, start_rad, mid, inner_radius)
            + arc_path(cx, cy, radius, mid, end_rad, inner_radius)
        )

    def _pt(angle: float, r: float) -> tuple[float, float]:
        return (
            cx + r * math.cos(angle - math.pi / 2),
            cy + r * math.sin(angle - math.pi / 2),
        )

    large_arc = 1 if (end_rad - start_rad) > math.pi else 0
    sx, sy = _pt(start_rad, radius)
    ex, ey = _pt(end_rad, radius)

    if inner_radius <= 0:
        return (
            f"M{_fmt(cx)},{_fmt(cy)} "
            f"L{_fmt(sx)},{_fmt(sy)} "
            f"A{_fmt(radius)},{_fmt(radius)} 0 {large_arc} 1 "
            f"{_fmt(ex)},{_fmt(ey)} Z"
        )

    isx, isy = _pt(start_rad, inner_radius)
    iex, iey = _pt(end_rad, inner_radius)
    return (
        f"M{_fmt(sx)},{_fmt(sy)} "
        f"A{_fmt(radius)},{_fmt(radius)} 0 {large_arc} 1 "
        f"{_fmt(ex)},{_fmt(ey)} "
        f"L{_fmt(iex)},{_fmt(iey)} "
        f"A{_fmt(inner_radius)},{_fmt(inner_radius)} 0 {large_arc} 0 "
        f"{_fmt(isx)},{_fmt(isy)} Z"
    )
