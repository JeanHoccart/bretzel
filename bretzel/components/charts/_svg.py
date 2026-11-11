"""Shared SVG primitives for the chart components.

Pure functions, with ONE exception, and it is named here because the
docstring lied for the length of a commit: :func:`format_value` reads
``text("chart.currency")`` for the currency symbol and
``text("chart.decimal")`` for the decimal mark, so it consults the
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
  but the byte-saving on long paths is meaningful and visually
  indistinguishable.
- Empty inputs (``[]``) return safe sentinels (``""`` for paths, the
  domain endpoints unchanged) — callers decide how to render the empty
  state.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable
from typing import Any

from bretzel.render import text

# ───────────────────────────────────────────────────────────────────────
# Value formatting
# ───────────────────────────────────────────────────────────────────────


class Localized(str):
    """A label the BROWSER writes in the page's language — the string
    itself is only the server's fallback, shown until the runtime starts.

    A date on a chart's axis is the case: its month's name and the order
    of day and month come from ``Intl`` (``$bz.dates.axis``), which the
    server does not have: ``strftime`` would say « Feb 02 » on a French
    page. Each sink that writes a label carries the twin with
    :func:`localized_attr`.
    """

    js: str

    def __new__(cls, fallback: str, js: str) -> Localized:
        label = super().__new__(cls, fallback)
        label.js = js
        return label


def label_js(label: str) -> str:
    """The JS expression of a label: its browser twin, or the string."""
    return label.js if isinstance(label, Localized) else json.dumps(label)


def localized_attr(label: str, attr: str | None = None) -> dict[str, str]:
    """The directive that lets the browser rewrite ``label``: ``bz-text``
    for a text node, ``bz-attr:<attr>`` for an attribute — nothing for a
    plain string."""
    if not isinstance(label, Localized):
        return {}
    return {f"bz-attr:{attr}" if attr else "bz-text": label.js}


def joined(*parts: str) -> str:
    """``parts`` glued together, keeping the browser twin of any of them."""
    plain = "".join(parts)
    if not any(isinstance(p, Localized) for p in parts):
        return plain
    return Localized(plain, " + ".join(label_js(p) for p in parts))


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
    - ``"percent"``    — ``0.42`` → ``"42%"`` (multiplies by 100), the
      shape from the ``number.percent`` text key (« 42 % » in French).
    - ``"currency"``   — ``1234.5`` → ``"$1,234.50"``. The symbol and its
      place come from the ``chart.currency`` text key, so an app writes
      ``translations={"fr": {"chart.currency": "{value} €"}}`` once; the
      marks from ``chart.thousands`` and ``chart.decimal``
      (« 1 234,50 € » in French).

    ``None`` falls back to terse ``"1234"`` (int-like) or ``"3.14"``
    (with decimals, trailing zeros stripped).

    Every decimal mark is the ``chart.decimal`` text key — ``"3,14"`` in
    a French app.

    ``unit`` (optional) appends a space-separated suffix —
    ``unit="ms"`` → ``"91 ms"``, ``unit="users"`` → ``"1.2k users"``.
    Skipped silently when ``fmt`` is a callable (the caller owns the
    full output) and when ``fmt="percent"`` (the ``%`` is already the
    unit). For ``fmt="currency"`` the suffix appends after the dollar
    amount — useful for cross-currency contexts where ``$ ... USD``
    avoids ambiguity.
    """
    if callable(fmt):
        out: Any = fmt(value)
        return out if isinstance(out, Localized) else str(out)
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
        base = base.replace(".", text("chart.decimal"))
    elif fmt == "percent":
        return text("number.percent", value=round(value * 100))
    elif fmt == "currency":
        # Both marks at once: "," then "." would turn one into the other.
        marks = {ord(","): text("chart.thousands"), ord("."): text("chart.decimal")}
        base = text("chart.currency", value=f"{value:,.2f}".translate(marks))
    else:
        base = _plain(value).replace(".", text("chart.decimal"))
    return f"{base} {unit}" if unit else base


def _plain(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def number(value: float) -> str:
    """A number as the page writes it: its thousands grouped, its decimal
    mark — « 48 240 », « 12,4 » in French, « 48,240 », « 12.4 » in
    English. At most two decimals, trailing zeros dropped, as
    :func:`format_value`. The value of a ``ui.stat``."""
    whole, _, decimals = _plain(value).partition(".")
    sign, digits = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    grouped = f"{int(digits):,}".replace(",", text("chart.thousands"))
    return sign + grouped + (text("chart.decimal") + decimals if decimals else "")


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


def widen(
    domain: tuple[float, float], values: Iterable[float],
    low: float | None = None, high: float | None = None,
) -> tuple[float, float]:
    """The domain stretched to cover ``[low, high]`` — the bounds an app
    asked for (``y_max=20``: a mean on 20 reads on 0–20). Never narrowed:
    a value past a bound pushes it (a 21/20 with a bonus stays seen). A
    bound replaces the domain's padding on its side, so ``y_max=20``
    with a 20/20 ends at 20, not at a padded 21 → 25."""
    lo, hi = domain
    seen = list(values)
    if low is not None:
        lo = min([low, *seen])
    if high is not None:
        hi = max([high, *seen])
    return lo, hi


def whole(values: Iterable[float]) -> bool:
    """Every value a whole number — counts: their axis steps by 1 at
    least (``compute_ticks(whole=True)``)."""
    return all(float(v).is_integer() for v in values)


def compute_ticks(
    domain_min: float,
    domain_max: float,
    target_count: int = 5,
    *,
    whole: bool = False,
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

    ``whole``: the values are counts — the step never goes under 1, so a
    chart of pupils per mark does not read « 0,5 » on its axis.
    """
    if domain_min == domain_max or target_count < 2:
        return [domain_min] if domain_min == domain_max else [domain_min, domain_max]
    span = _nice_number(domain_max - domain_min, round_to_one_of=False)
    step = _nice_number(span / (target_count - 1), round_to_one_of=True)
    if whole:
        step = max(step, 1.0)
    start = math.floor(domain_min / step) * step
    end = math.ceil(domain_max / step) * step
    ticks: list[float] = []
    value = start
    # Tolerance avoids float drift dropping the last tick.
    while value <= end + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


#: The steps a time axis is graduated in, in seconds: a minute, a quarter
#: of an hour, an hour, a few hours, a day, a week. Beyond two months the
#: nice-number ticks of :func:`compute_ticks` read well enough (« janv.
#: 01 »), so the list stops there.
_TIME_STEPS = (60, 300, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600, 12 * 3600,
               86400, 2 * 86400, 7 * 86400, 14 * 86400)


def compute_time_ticks(domain_min: float, domain_max: float,
                       target_count: int = 5) -> list[float] | None:
    """Ticks of a TIME axis, on round moments: whole hours, midnights,
    Mondays — inside the domain.

    The x of a time axis is a POSIX timestamp, and the nice numbers of
    :func:`compute_ticks` are nice in SECONDS: a day would read « 22h20,
    3h53, 9h26 ». Here the step is
    picked from :data:`_TIME_STEPS` and the first tick is the first
    boundary of that step in local time (the timestamps are local:
    ``series.to_x``). ``None`` past the last step: the caller keeps the
    numeric ticks.
    """
    from datetime import datetime, timedelta

    span = domain_max - domain_min
    if span <= 0:
        return None
    step = next((s for s in _TIME_STEPS if span / s <= target_count), None)
    if step is None:
        return None
    start = datetime.fromtimestamp(domain_min)
    if step >= 7 * 86400:
        first = (start - timedelta(days=start.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
    elif step >= 86400:
        first = start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
        into = (start - midnight).total_seconds()
        first = midnight + timedelta(seconds=(into // step) * step)
    ticks: list[float] = []
    moment = first
    while moment.timestamp() <= domain_max:
        if moment.timestamp() >= domain_min:
            ticks.append(moment.timestamp())
        # Calendar arithmetic, not seconds: a day stays a day across a
        # change of summer time.
        moment = moment + timedelta(seconds=step) if step < 86400 else             moment + timedelta(days=step // 86400)
    return ticks


def _fmt(n: float) -> str:
    """Round to 2 decimals and strip trailing zeros for terse SVG output."""
    return f"{round(n, 2):g}"


# ───────────────────────────────────────────────────────────────────────
# The horizontal axis is a PERCENTAGE of the plot
# ───────────────────────────────────────────────────────────────────────
#
# The series charts (bar / line / scatter) fill their container. The
# server cannot know that width, so no horizontal coordinate is written
# in pixels: the ``<svg>`` IS the plot rectangle (its margins are CSS,
# cf. ``_layers.plot_svg``), and every x is a share of it — ``x="37.5%"``
# resolves against the svg's viewport, whatever it measures. The
# vertical axis stays in pixels: its extent is the ``size=`` step.
#
# A fixed ``viewBox`` could not do it: it scales the whole drawing, so a
# chart 600 wide in a 1000-px card either letterboxes (``meet``) or
# swells its text by 67 %. A pixel offset from a percentage goes through
# ``dx`` on a ``<text>`` (``x="100%" dx="-4"``); a plain number is a
# pixel offset from the plot's LEFT edge (``x="-6"``, left of the axis).

#: The span of the horizontal range, in percent of the plot width.
PLOT_SPAN = 100.0


def _pct(n: float) -> str:
    """A horizontal coordinate or length, in percent of the plot width."""
    return f"{_fmt(n)}%"


#: The average advance of a glyph, in ems. The server has no font
#: metrics; 0.6 em covers digits and lower-case letters of the sans
#: stacks the themes ship (digits measure ~0.55 em) with a margin, so
#: an estimate errs on the side of a little extra room — never a clip.
_GLYPH_EM = 0.6


def text_width(label: str, font_px: float) -> float:
    """Estimated rendered width of ``label`` at ``font_px``, in pixels."""
    return len(label) * font_px * _GLYPH_EM


def axis_margin(labels: Iterable[str], font_px: float, *, floor: float) -> int:
    """The room left of the plot for right-aligned axis labels.

    The labels end 6 px left of the axis (``x="-6"``, ``text-anchor:
    end``), so the margin must hold the WIDEST of them plus that gap. A
    constant margin would leave a long label (``y_unit=" requests/s"``)
    outside the chart, cut by any card with an ``overflow`` other than
    visible. ``floor`` is the width kept when the labels are short.
    """
    widest = max((text_width(label, font_px) for label in labels), default=0.0)
    return max(int(floor), math.ceil(widest + 6 + 2))


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


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def smooth_path(points: list[tuple[float, float]]) -> str:
    """SVG ``d`` for a monotone cubic curve through ``points``.

    The algorithm D3 ships as ``curveMonotoneX`` (Steffen, 1990): the
    curve passes through every point and never leaves the interval of
    two neighbours — no dip under a flat stretch, no peak above the
    highest close. A smooth line that draws a value the data never had
    is lying, and a Catmull-Rom does as soon as the x steps are uneven
    (a week-end in a series of closes).

    Needs x increasing, as every chart's x is. Under 3 points, a
    straight path. The control points are affine in x and y, so the
    stretched frame of ``ui.line_chart`` (x scaled alone) keeps the
    curve's shape.
    """
    n = len(points)
    if n < 3:
        return line_path(points)
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    steps = [xs[i + 1] - xs[i] for i in range(n - 1)]
    slopes = [(ys[i + 1] - ys[i]) / steps[i] if steps[i] else 0.0 for i in range(n - 1)]
    tangents = [0.0] * n
    for i in range(1, n - 1):
        h0, h1, s0, s1 = steps[i - 1], steps[i], slopes[i - 1], slopes[i]
        if h0 + h1 == 0:
            continue
        through = (s0 * h1 + s1 * h0) / (h0 + h1)
        tangents[i] = (_sign(s0) + _sign(s1)) * min(abs(s0), abs(s1), 0.5 * abs(through))
    # The ends: the tangent that keeps the first (last) segment's own
    # slope, as D3's ``slope2``.
    tangents[0] = (3 * slopes[0] - tangents[1]) / 2 if steps[0] else tangents[1]
    tangents[-1] = (3 * slopes[-1] - tangents[-2]) / 2 if steps[-1] else tangents[-2]
    # Clamp the ends too: an end tangent past three times its slope
    # would bend the first segment out of its interval.
    for i, s in ((0, slopes[0]), (n - 1, slopes[-1])):
        if _sign(tangents[i]) != _sign(s):
            tangents[i] = 0.0
        elif abs(tangents[i]) > 3 * abs(s):
            tangents[i] = 3 * s
    out = [f"M{_fmt(xs[0])},{_fmt(ys[0])}"]
    for i in range(n - 1):
        third = steps[i] / 3
        out.append(
            f"C{_fmt(xs[i] + third)},{_fmt(ys[i] + tangents[i] * third)} "
            f"{_fmt(xs[i + 1] - third)},{_fmt(ys[i + 1] - tangents[i + 1] * third)} "
            f"{_fmt(xs[i + 1])},{_fmt(ys[i + 1])}"
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
            # ``L``-to-centre cuts. Two wedges concatenated would
            # overlap the centre-to-edge segments and show a vertical
            # seam through the middle when stroked between slices.
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
