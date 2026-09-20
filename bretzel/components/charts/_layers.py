"""SVG layers shared by the charts — the pieces that build ``Element``.

Distinct from :mod:`._svg`, which is deliberately I/O-free (pure maths,
no Bretzel import, no ``Element`` construction). Here we assemble nodes,
so it could not go there.

Three layers, each copied from one chart to the next (audit F10, F43,
F45):

- :func:`render_empty_state` — the empty state, a ``ui.empty_state`` in
  a box the size of the plot;
- :func:`render_axis_layer` — the vertical axis + gridlines + labels;
- :func:`render_static_legend` — the non-interactive legend.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.components.base import reject_component
from bretzel.components.charts._svg import _fmt, format_value
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode


def reject_empty_text_component(value: Any, *, owner: str) -> None:
    """``empty_text=`` is not a slot — the four charts refuse it.

    The reason is structural and reads in :func:`render_empty_state`
    just below: the text goes to TWO places, the ``EmptyState``'s title
    **and** the box's ``aria-label``. An HTML attribute only carries a
    string, so a Component would be serialised there as its Python
    ``repr`` for the screen reader — it is word for word the argument by
    which ``file_upload.label`` already refuses.

    ⚠️ The reason survived the render change (SVG → ``EmptyState``,
    2026-09-07) because it bears on the DOUBLE use of the text, not on
    the tag. It said "an SVG ``<text>`` and the ``<svg>``'s
    ``aria-label``"; both destinations still exist.

    Written once here rather than four times in the charts: the reason
    is the same for all four, and a reason copied four times drifts
    (audit F10/F43/F45, this module's pattern).
    """
    reject_component(
        value,
        owner=owner,
        prop="empty_text",
        because=(
            "this text ALSO goes into the box's ``aria-label``, and an "
            "HTML attribute can only carry a string (the Component would "
            "be announced there to the screen reader under its Python "
            "repr)."
        ),
        instead=(
            "For a composed empty state, that is ``empty=``: "
            "``ui.bar_chart(data, empty=lambda: ui.button('Import'))``."
        ),
    )


def render_empty_state(
    component: Any,
    *,
    width: int,
    height: int,
    kind: str,
    message: str,
    icon: str | None,
    description: str | None,
    escape: Callable[[], Any] | None,
    size_key: str,
) -> Element:
    """A chart's empty state: a ``ui.empty_state`` in a box the size of
    the plot, or the escape hatch the author placed.


    **Why it is no longer a centred SVG ``<text>``.** The four charts
    offered only ``empty_text``, when ``table``, ``datatable`` and
    ``diagram`` offer all four — three depths for one need (audit of
    2026-09-06, § 1.3). An empty chart said "No data" and nothing else:
    neither why, nor what to do. Composing :class:`EmptyState`, as
    ``diagram`` does, aligns the four with the rest of the catalogue and
    gives them the theme's icon, title hierarchy and spacing without
    rewriting them.

    ⚠️ **``role="img"`` + ``aria-label`` on the BOX**, not on the
    content, and that is what preserves fix F24: an empty scatter
    announced itself as "Line chart" when the helper was private to
    line_chart. ``kind`` therefore stays mandatory, and ``role="img"``
    makes the descendants presentational — exactly the semantics the
    ``<svg role="img">`` had, without which the screen reader would lose
    the component's identity while gaining the message.

    ⚠️ **``_detach_from_parent`` BEFORE ``render()``.** A Component built
    in a ``render()`` registers itself with the ACTIVE parent and leaks
    — traps.md's "Icon built in render() without detach" trap, paid for
    by ``diagram`` before us.
    """
    from bretzel.components.base import coerce_children
    from bretzel.components.base.component import Component
    from bretzel.components.feedback.empty_state import EmptyState

    box_attrs = {
        "class": "flex items-center justify-center w-full",
        "style": f"min-height:{height}px",
        "role": "img",
        "aria-label": f"{kind} — {message}",
    }
    if escape is not None:
        return Element(
            tag="div", attrs=box_attrs, children=coerce_children(escape())
        )
    empty = EmptyState(
        message,
        icon=icon,
        description=description,
        # The empty state follows the chart's step: without that a
        # ``size=`` would change NOTHING on an empty chart — the dead
        # kwarg this repository hunts. Same reason, same line as
        # ``diagram``.
        size=size_key,
    )
    Component._detach_from_parent(empty)
    return Element(tag="div", attrs=box_attrs, children=(empty.render(),))


def render_axis_layer(
    slot: Callable[..., str],
    ticks: list[float],
    y_scale: Callable[[float], float],
    plot_left: float,
    plot_right: float,
    axis_font: int,
    show_axis: bool,
    show_gridlines: bool,
    y_format: Any,
    y_unit: str | None = None,
    *,
    group_class: str,
) -> Element:
    """The vertical axis: the axis line, the horizontal gridlines, the
    tick labels.

    ``group_class`` is the container ``<g>``'s class. It is parameterised
    — and not unified — because line and bar emit different names
    (``bz-line-axes`` / ``bz-bar-axes``) that no framework CSS or JS
    reads: merging them would gain nothing and would break a possible
    application selector. Unifying them stays possible, it will be a
    conscious gesture.

    (BarChart carried a copy identical to the character, modulo that
    class name and the line break — audit F10.)
    """
    gridline_cls = slot("gridline")
    axis_cls = slot("axis")
    label_cls = slot("axis_label")
    children: list[Element] = []
    if show_axis:
        children.append(Element(tag="line", attrs={
            "class": axis_cls,
            "x1": _fmt(plot_left), "x2": _fmt(plot_left),
            "y1": _fmt(y_scale(ticks[0])),
            "y2": _fmt(y_scale(ticks[-1])),
        }, children=()))
    for tick in ticks:
        ty = y_scale(tick)
        if show_gridlines:
            children.append(Element(tag="line", attrs={
                "class": gridline_cls,
                "x1": _fmt(plot_left), "x2": _fmt(plot_right),
                "y1": _fmt(ty), "y2": _fmt(ty),
            }, children=()))
        if show_axis:
            children.append(Element(tag="text", attrs={
                "class": label_cls,
                "x": _fmt(plot_left - 6), "y": _fmt(ty),
                "font-size": str(axis_font),
                "text-anchor": "end",
                "dominant-baseline": "middle",
            }, children=(TextNode(format_value(tick, y_format, y_unit)),)))
    return Element(tag="g", attrs={"class": group_class},
                   children=tuple(children))


def render_static_legend(
    slot: Callable[..., str],
    entries: Sequence[tuple[str | None, str]],
) -> Element:
    """The non-interactive legend: one dot + one label per entry.

    ``entries`` is a sequence of ``(colour, label)`` — the series charts
    pass ``(s.color, s.name)``, the pie passes ``(palette[i], label)``.
    It is the only thing that differed between the two copies (audit
    F45); the interactive version (line / scatter, with series toggle)
    stays separate, it has a real behaviour.
    """
    label_cls = slot("legend_label")
    children: list[Element] = []
    for colour, label in entries:
        children.append(Element(tag="div", attrs={
            "class": "flex items-center gap-2",
        }, children=(
            Element(tag="span", attrs={"class": slot("legend_dot", colour)},
                    children=()),
            Element(tag="span", attrs={"class": label_cls},
                    children=(TextNode(label),)),
        )))
    return Element(tag="div", attrs={"class": slot("legend")},
                   children=tuple(children))


__all__ = [
    "render_axis_layer",
    "render_empty_state",
    "render_static_legend",
]
