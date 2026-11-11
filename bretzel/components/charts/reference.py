"""Reference lines: the ``Reference`` dataclass and how the charts draw it.

A reference line is a horizontal rule rendered behind the data,
usually annotating a goal, a release marker, a baseline, or a
threshold. The label sits at the right edge of the plot area so it
doesn't compete with the data.

API ::

    ui.line_chart(
        revenue,
        y_reference_lines=[
            Reference(value=1000, label="Q3 target"),
            Reference(value=2000, label="Stretch", color="success"),
        ],
    )

``ui.line_chart(x_reference_lines=…)`` takes the same shapes for
VERTICAL lines, at moments rather than values : the value is then an
x — a number or a date, like the chart's x values ::

    ui.line_chart(prices, x_reference_lines=[
        (date(2026, 10, 13), "achat"),
        Reference(value=date(2026, 11, 2), label="vente", color="error"),
    ])

A bare value is a line without a label (``y_reference_lines=[4]``) ;
a tuple ``(value, label)`` names it ; ``(value, label,
color)`` lets the app pin the colour. ``color=None`` falls back to
``"muted"`` so the reference doesn't compete with the series'
palette colours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.charts._svg import PLOT_SPAN, _fmt, _pct, format_value
from bretzel.components.charts.series import x_bound
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


@dataclass(frozen=True, slots=True)
class Reference:
    """One reference line : on the y axis, or at an x (``x_reference_lines``)."""

    value: float | date
    label: str = ""
    color: str | None = None


def coerce_references(owner: str, refs: Any) -> list[Reference]:
    """Normalise ``y_reference_lines=`` into a list of ``Reference``.

    Accepts ``Reference`` instances, a bare number (a line without a
    label), ``(value, label)`` 2-tuples, and ``(value, label, color)``
    3-tuples, the value a number. ``None`` /
    empty → no refs. Anything else is refused : a bare string would be
    walked letter by letter and drop out in silence.
    """
    if not refs:
        return []
    if isinstance(refs, (str, bytes, dict)):
        raise ComponentUsageError(
            f"{owner}: y_reference_lines={refs!r} — expected a list of (value, "
            "label), (value, label, color) or Reference.")
    out: list[Reference] = []
    for r in refs:
        if isinstance(r, Reference):
            value, label, color = r.value, r.label, r.color
        elif isinstance(r, (tuple, list)) and r:
            value = r[0]
            label = str(r[1]) if len(r) > 1 and r[1] is not None else ""
            color = str(r[2]) if len(r) > 2 and r[2] else None
        elif isinstance(r, (int, float)) and not isinstance(r, bool):
            # A bare value: the line, without a label (``[4]``).
            value, label, color = r, "", None
        else:
            raise ComponentUsageError(
                f"{owner}: y_reference_lines item {r!r} — expected a number, "
                "(value, label), (value, label, color) or a Reference.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ComponentUsageError(
                f"{owner}: y_reference_lines value {value!r} — expected a number, "
                "on the y axis.")
        out.append(Reference(value=float(value), label=label, color=color))
    return out


def coerce_x_references(owner: str, refs: Any) -> list[Reference]:
    """Normalise ``x_reference_lines=`` : the same shapes as
    ``y_reference_lines=`` — a ``Reference``, a bare x, ``(x, label)``,
    ``(x, label, color)`` — with an x that is a number or a date, turned into the
    drawn x (a date's timestamp, as the x values are). Sorted by x, so
    the labels can step down when two marks are close."""
    if not refs:
        return []
    if isinstance(refs, (str, bytes, dict)):
        raise ComponentUsageError(
            f"{owner}: x_reference_lines={refs!r} — expected a list of (x, label), "
            "(x, label, color) or Reference.")
    out: list[Reference] = []
    for r in refs:
        if isinstance(r, Reference):
            value, label, color = r.value, r.label, r.color
        elif isinstance(r, (tuple, list)) and r:
            value = r[0]
            label = str(r[1]) if len(r) > 1 and r[1] is not None else ""
            color = str(r[2]) if len(r) > 2 and r[2] else None
        elif not isinstance(r, (str, bytes, bool)):
            # A bare x (a number or a date): the mark says its moment.
            value, label, color = r, "", None
        else:
            raise ComponentUsageError(
                f"{owner}: x_reference_lines item {r!r} — expected an x, (x, label), "
                "(x, label, color) or a Reference, x a number or a date.")
        drawn = x_bound(owner, "x_reference_lines", value)
        out.append(Reference(value=drawn, label=label, color=color))
    return sorted(out, key=lambda ref: float(ref.value))


def reference_text(r: Reference, y_format, y_unit: str | None) -> str:
    """A reference's label: its name, then its value in parens — the
    value keeps the eye anchored on the threshold. Formatted like the
    ticks, so it reads as the same scale."""
    value_str = format_value(float(r.value), y_format, y_unit)
    return f"{r.label} ({value_str})" if r.label else value_str


def render_reference_lines(
    slot, refs: list[Reference], y_scale,
) -> Element:
    """Horizontal dashed lines for threshold annotations.

    ``color=None`` on a ref falls back to ``"muted"`` so a reference
    line without an explicit colour doesn't compete with the series
    palette.

    The LINES only: they are painted behind the data, their labels in
    front (:func:`render_reference_labels`). The two lived in one
    group, so the label shared the line's depth — and on a bar chart it
    passed under the bars.
    """
    children: list[Element] = []
    for r in refs:
        ty = y_scale(float(r.value))
        children.append(Element(tag="line", attrs={
            "class": slot("reference_line", r.color or "muted"),
            "x1": "0", "x2": "100%",
            "y1": _fmt(ty), "y2": _fmt(ty),
            "stroke-dasharray": "4 4",
        }, children=()))
    return Element(
        tag="g", attrs={"class": "bz-line-refs"},
        children=tuple(children),
    )


def render_reference_labels(
    slot, refs: list[Reference], y_scale, axis_font: int,
    y_format, y_unit: str | None,
) -> Element:
    """The references' labels, just above each line at the plot's right
    edge — painted AFTER the data, so nothing covers them."""
    children: list[Element] = []
    for r in refs:
        children.append(Element(tag="text", attrs={
            "class": slot("reference_label", r.color or "muted"),
            "x": "100%", "dx": "-4",
            "y": _fmt(y_scale(float(r.value)) - 4),
            "text-anchor": "end",
            "font-size": str(axis_font),
        }, children=(TextNode(reference_text(r, y_format, y_unit)),)))
    return Element(
        tag="g", attrs={"class": "bz-line-ref-labels"},
        children=tuple(children),
    )


def vertical_rule(cls: str, x: str, plot_top: float, plot_bottom: float) -> Element:
    """A dashed vertical line across the plot, at ``x``."""
    return Element(tag="line", attrs={
        "class": cls,
        "x1": x, "x2": x,
        "y1": _fmt(plot_top), "y2": _fmt(plot_bottom),
        "stroke-dasharray": "4 4",
    }, children=())


def render_x_reference_lines(
    slot, refs: list[Reference], x_scale, plot_top: float, plot_bottom: float,
    *,
    group_class: str = "bz-line-x-refs",
) -> Element:
    """Vertical dashed lines at moments — behind the data, like the
    horizontal ones (:func:`render_reference_lines`)."""
    children = [
        vertical_rule(slot("reference_line", r.color or "muted"),
                      _pct(x_scale(float(r.value))), plot_top, plot_bottom)
        for r in refs
    ]
    return Element(tag="g", attrs={"class": group_class}, children=tuple(children))


#: Two marks closer than this (in % of the plot's width) put their
#: labels on two rows, or the words would run into each other.
_X_LABEL_CROWD = 14.0


def render_x_reference_labels(
    slot, refs: list[Reference], x_scale, plot_top: float, axis_font: int,
    x_format, x_unit: str | None,
) -> Element:
    """Each mark's label at the top of its line, painted after the data.
    Its name, or its x written like the axis when it has none. A label
    in the right quarter reads leftwards, so it stays in the plot ; a
    mark close to the previous one steps its label down a row."""
    children: list[Element] = []
    previous: float | None = None
    row = 0
    for r in refs:
        at = x_scale(float(r.value))
        row = (row + 1) % 2 if previous is not None and at - previous < _X_LABEL_CROWD else 0
        previous = at
        words = r.label or format_value(float(r.value), x_format, x_unit)
        right = at > PLOT_SPAN * 0.75
        children.append(Element(tag="text", attrs={
            "class": slot("reference_label", r.color or "muted"),
            "x": _pct(at), "dx": "-4" if right else "4",
            "y": _fmt(plot_top + axis_font * (1 + row * 1.3)),
            "text-anchor": "end" if right else "start",
            "font-size": str(axis_font),
        }, children=(TextNode(words),)))
    return Element(
        tag="g", attrs={"class": "bz-line-x-ref-labels"},
        children=tuple(children),
    )
