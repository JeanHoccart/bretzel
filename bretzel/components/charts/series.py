"""Light ``Series`` dataclass for multi-series chart payloads.

A chart's ``data=`` kwarg accepts three shapes :

- ``list[number]``           — single series, x = index (sparklines only)
- ``list[tuple[x, y]]``      — single series with explicit x values
- ``list[Series]``           — N series for bar / line charts

``Series`` carries an optional ``color=`` override so an app can pin a
specific series to a semantic color (``"success"`` for the active
metric, ``"muted"`` for the comparison baseline). When ``color=None``
the chart picks from its theme palette in declaration order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.charts._svg import Localized


@dataclass(frozen=True, slots=True)
class Series:
    """One data series in a multi-series chart."""

    name: str
    data: list[float | tuple[float, float]] = field(default_factory=list)
    color: str | None = None


def with_series(payload: dict[str, Any], s: Series, series: list[Series]) -> dict[str, Any]:
    """A clicked element's data, plus its series when there are several:
    a bar or a point belongs to one, and the rest does not say which."""
    return {**payload, "series": s.name} if len(series) > 1 else payload


def to_timestamp(x: Any) -> float:
    """Convert a ``date`` / ``datetime`` / number to a POSIX timestamp.

    ``date`` is widened to midnight UTC so ``timestamp()`` doesn't
    depend on the host TZ for day-precision inputs.
    """
    if isinstance(x, datetime):
        return x.timestamp()
    if isinstance(x, date):
        return datetime(x.year, x.month, x.day).timestamp()
    return float(x)


def has_points(series: list[Series]) -> bool:
    """Is there anything to draw? One series with a point is enough."""
    return any(s.data for s in series)


def first_x(data: Any) -> Any:
    """The first x the caller gave, read on the raw ``data=``, whichever
    series holds it: a series may be empty. ``None`` with no explicit x (a
    bare list of numbers, or nothing)."""
    for item in data or ():
        for point in item.data if isinstance(item, Series) else (item,):
            if isinstance(point, (tuple, list)) and len(point) >= 2:
                return point[0]
    return None


def is_date_axis(data: Any) -> bool:
    """Did the caller give ``date`` / ``datetime`` x values?"""
    return isinstance(first_x(data), date)


def x_back(data: Any) -> Any:
    """The drawn x turned back into what the app gave, for
    ``on_item_click(x, y)`` — an ``int`` an int; a date its ISO text
    (``2026-09-01``), as a handler's bound values are JSON."""
    sample = first_x(data)
    if isinstance(sample, datetime):
        return lambda ts: datetime.fromtimestamp(ts).isoformat()
    if isinstance(sample, date):
        return lambda ts: datetime.fromtimestamp(ts).date().isoformat()
    # A bare list of numbers: x is the index.
    if sample is None or isinstance(sample, int):
        return lambda x: int(x) if float(x).is_integer() else x
    return lambda x: x


def x_bound(owner: str, name: str, value: Any) -> float | None:
    """``x_min`` / ``x_max``: a number or a date, as the x values are —
    anything else said, not raised bare from ``float()``."""
    if value is None:
        return None
    if isinstance(value, (int, float, date)) and not isinstance(value, bool):
        return to_timestamp(value)
    raise ComponentUsageError(
        f"{owner}: {name}={value!r} — expected a number or a date, like the "
        "x values.")


def bad_point(owner: str, item: Any, shape: str) -> ComponentUsageError:
    """A point of ``data=`` that is not a point: said, not skipped. A list
    of ``{"label", "value"}`` dicts must not draw « No data », nor
    a ``None`` mean vanish from the chart."""
    return ComponentUsageError(
        f"{owner}: {item!r} is not a point of data= — expected {shape}. "
        "Leave out the points without a value (None) before passing them."
    )


def coerce_xy_series(
    data: Any,
    palette: tuple,
    *,
    default_color: str,
    owner: str,
    allow_index: bool,
    allow_gaps: bool = False,
) -> list[Series]:
    """Normalise a chart's ``data=`` into ``list[Series]`` of ``(x, y)``.

    Accepts the three documented shapes — ``list[Series]``,
    ``list[(x, y)]``, ``list[number]`` — converts x values through
    :func:`to_timestamp` and cycles ``palette`` for series that carry no
    ``color=``.

    Two flags carry the whole difference between LineChart and
    ScatterChart :

    - ``allow_index`` : a bare ``list[number]`` means "x = index" on a
      line, and means nothing on a scatter (a cloud needs both
      coordinates), where such an item is skipped.
    - ``allow_gaps`` : a ``None`` y is a HOLE on a line — the curve
      stops there and starts again after. A cloud has no line to break :
      there, a ``None`` is refused.

    The series of a line need not share their x values : a stock and an
    index have different holidays. Each series is drawn on its own x ; the
    chart reads them on the union of all of them.
    """
    if not data:
        return []
    if isinstance(data[0], Series):
        out: list[Series] = []
        for i, s in enumerate(data):
            colour = s.color or palette[i % len(palette)]
            try:
                pairs = [(to_timestamp(x), _y(y, allow_gaps)) for x, y in s.data]
            except (TypeError, ValueError):
                bad = next(p for p in s.data if not _readable_xy(p, allow_gaps))
                raise bad_point(owner, bad, _pair_shape(allow_gaps)) from None
            out.append(Series(name=s.name, data=pairs, color=colour))
        return out

    shape = ("a number, or an (x, y) pair" if allow_index
             else _pair_shape(allow_gaps))
    if allow_gaps:
        shape += " (None for a hole)"
    pairs: list[tuple] = []
    for i, item in enumerate(data):
        try:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                pairs.append((to_timestamp(item[0]), _y(item[1], allow_gaps)))
            elif allow_index and not isinstance(item, (tuple, list, dict, str)):
                pairs.append((float(i), _y(item, allow_gaps)))
            else:
                raise bad_point(owner, item, shape)
        except (TypeError, ValueError):
            raise bad_point(owner, item, shape) from None
    return [Series(name="", data=pairs, color=default_color)]


def runs_between_holes(
    data: list[tuple[float, float | None]],
) -> list[list[tuple[float, float]]]:
    """The stretches of a series between its holes (``None`` y), in x
    order — one sub-path each, so a curve stops at a hole instead of
    bridging it. Shared by ``ui.line_chart`` and ``ui.sparkline``: one
    reading of a ``None`` for every line."""
    runs: list[list[tuple[float, float]]] = [[]]
    for x, y in sorted(data, key=lambda pt: pt[0]):
        if y is None:
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append((x, y))
    return [run for run in runs if run]


def gap_y(value: Any) -> float | None:
    """A y as a number, or ``None`` — a hole."""
    return _y(value, True)


def _y(value: Any, allow_gaps: bool) -> float | None:
    """A y as a number, or ``None`` — a hole — where holes are allowed."""
    if value is None and allow_gaps:
        return None
    return float(value)


def _pair_shape(allow_gaps: bool) -> str:
    return ("an (x, y) pair of numbers or dates, y None for a hole" if allow_gaps
            else "an (x, y) pair of numbers or dates")


def _readable_xy(point: Any, allow_gaps: bool = False) -> bool:
    try:
        x, y = point
        to_timestamp(x), _y(y, allow_gaps)
    except (TypeError, ValueError):
        return False
    return True


def coloured_slot(component: Any, name: str, override: str | None,
                  fallback: str) -> str:
    """A chart slot's class, PLUS its colour's bridge.

    A chart is the only component whose **several children carry
    different colours**: one series per colour, on a root that has only
    one. The bridge the base layer sets on the root therefore cannot
    serve them all.

    The themes paint themselves with steps, so a slot's class does not
    carry the colour at all: ``fill-(--bz-solid)`` is the same for every
    series. It is the bridge class, added here, that says which. Without
    it, every series of one chart would render in the root's colour.

    ``override`` is the SERIES' colour (``Series(color=…)``),
    ``fallback`` the component's.

    **The bridge is only added if there is an override.** With no
    override the colour is the component's, so the one of the bridge the
    base layer has already set on the root: repeating it on every
    `<line>`, every axis label and every gridline would weigh the SVG
    down for nothing. Without that guard, the ``crosshair`` slot, which
    speaks of no colour, would come out with a ``bz-c-primary`` stuck on
    it.
    """
    classes = component.compose_class(name)
    if override is None:
        return classes

    from bretzel.theme.bridges import bridge_class

    return f"{classes} {bridge_class(override)}"


def _auto_date_format(span_seconds: float):
    """Pick an x-axis tick formatter based on the visible time span.

    Same rules every dashboard ships : seconds-precision on tight
    windows, day on multi-day, month on multi-year. Returns a
    callable suitable for ``format_value(..., fmt=callable, unit)``.
    """
    # "The last 24 hours" spans a day EXACTLY (a point at each end), or a
    # little more: it is the most common window of all, and in days it
    # reads « 07 nov. 07 nov. 07 nov. ».
    if span_seconds <= 60 * 60 * 24 * 1.1:    # up to a day → "HH:MM"
        fmt, style = "%H:%M", "time"
    elif span_seconds < 60 * 60 * 24 * 365:   # < 1 an → "Mon DD"
        fmt, style = "%b %d", "day"
    elif span_seconds < 60 * 60 * 24 * 365 * 5:   # < 5 years → "Mon YYYY"
        fmt, style = "%b %Y", "month"
    else:                                          # multi-year → "YYYY"
        fmt, style = "%Y", "year"

    def _fmt_date(moment: datetime) -> str:
        # The browser writes it in the page's language (« 02 févr. »,
        # « 14h30 »); ``strftime`` is only the fallback before it starts.
        stamp = moment.isoformat(timespec="minutes")
        return Localized(moment.strftime(fmt), f"$bz.dates.axis('{stamp}', '{style}')")
    return _fmt_date


def as_date_formatter(fn):
    """Make a time-axis formatter receive a ``datetime``.

    On a date axis, the x values are converted to POSIX timestamps
    before being scaled. Without this wrapper ``x_format=`` would receive
    a **float**, and the caller would have to redo
    ``datetime.fromtimestamp`` before being able to format anything. The
    component knows it is a date: it is its job to return it.

    Applies ONLY when the axis is detected as temporal. On a numeric
    axis, ``x_format=`` still receives the number.
    """
    def _wrapped(ts: float) -> str:
        out = fn(datetime.fromtimestamp(ts))
        return out if isinstance(out, Localized) else str(out)
    return _wrapped


def resolve_date_axis_format(data: Any, series: list[Series], x_format: Any):
    """The effective x-axis formatter, and whether the axis is temporal.

    Shared by LineChart and ScatterChart, which each had a copy of it
    word for word — and that copy had to be edited on both sides in the
    same commit, which is the signal.

    Three rules, in that order:

    1. a non-temporal axis → we touch nothing, ``x_format=`` receives the
       number as always;
    2. nothing supplied → the automatic formatter, chosen on the visible
       SPAN (HH:MM under a day, "Mon DD" under a year…);
    3. a *callable* — theirs or ours — receives a ``datetime`` and not
       the scaling's POSIX timestamp.

    ⚠️ The point that cost a defect: ``x_format=`` ALSO accepts the
    string shortcuts (``"abbreviated"``, ``"percent"``, ``"currency"``).
    A first version only kept the caller's value if it was callable — so
    a string was **thrown away in silence** on a date axis, and the ticks
    came out identical to the default's. A string does not make much
    sense on a temporal axis, but ignoring it without a word is worse
    than honouring it.
    """
    if not is_date_axis(data):
        return x_format, False
    if x_format is None:
        xs_all = [x for s in series for x, _ in s.data]
        x_format = _auto_date_format((max(xs_all) - min(xs_all)) if xs_all else 0.0)
    if callable(x_format):
        x_format = as_date_formatter(x_format)
    return x_format, True
