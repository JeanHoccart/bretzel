"""SVG layers shared by the charts — the pieces that build ``Element``.

Distinct from :mod:`._svg`, which is deliberately I/O-free (pure maths,
no Bretzel import, no ``Element`` construction). Here we assemble nodes,
so it could not go there.

Three layers, shared by the charts:

- :func:`render_empty_state` — the empty state, a ``ui.empty_state`` in
  a box the size of the plot;
- :func:`render_axis_layer` — the vertical axis + gridlines + labels;
- :func:`render_static_legend` — the non-interactive legend.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.components.base import reject_component
from bretzel.components.base.scope_wiring import bool_attr
from bretzel.components.charts._svg import (
    Localized,
    _fmt,
    _pct,
    compute_ticks,
    compute_time_ticks,
    format_value,
    localized_attr,
)
from bretzel.components.charts.series import Series
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text


def reject_empty_text_component(value: Any, *, owner: str) -> None:
    """``empty_text=`` is not a slot — the four charts refuse it.

    The reason is structural and reads in :func:`render_empty_state`
    just below: the text goes to TWO places, the ``EmptyState``'s title
    **and** the box's ``aria-label``. An HTML attribute only carries a
    string, so a Component would be serialised there as its Python
    ``repr`` for the screen reader — it is word for word the argument by
    which ``file_upload.label`` already refuses.

    Written once here rather than four times in the charts: the reason
    is the same for all four, and a reason copied four times drifts.
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
    *,
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


    **Why not a centred SVG ``<text>``.** A bare "No data" says neither
    why, nor what to do. Composing :class:`EmptyState`, as ``diagram``
    does, aligns the four charts with the rest of the catalogue and gives
    them the theme's icon, title hierarchy and spacing without rewriting
    them.

    ⚠️ **``role="img"`` + ``aria-label`` on the BOX**, not on the
    content. ``kind`` is mandatory, or an empty scatter would announce
    itself as another chart, and ``role="img"`` makes the descendants
    presentational — exactly the semantics of the ``<svg role="img">``,
    without which the screen reader would lose the component's identity
    while gaining the message.

    ⚠️ **``_detach_from_parent`` BEFORE ``render()``.** A Component built
    in a ``render()`` registers itself with the ACTIVE parent and leaks
    — the trap traps.md § "Icon construit dans `render()` sans
    détachement", paid for by ``diagram`` before us.
    """
    from bretzel.components.base import call_render, coerce_children
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
            tag="div", attrs=box_attrs, children=coerce_children(call_render(escape))
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

    The svg is the plot (cf. :func:`plot_svg`): the axis sits at ``x=0``,
    the gridlines run to ``100%``, the labels end 6 px left of the axis,
    in the margin :func:`~._svg.axis_margin` sized for them.
    """
    gridline_cls = slot("gridline")
    axis_cls = slot("axis")
    label_cls = slot("axis_label")
    children: list[Element] = []
    if show_axis:
        children.append(Element(tag="line", attrs={
            "class": axis_cls,
            "x1": "0", "x2": "0",
            "y1": _fmt(y_scale(ticks[0])),
            "y2": _fmt(y_scale(ticks[-1])),
        }, children=()))
    for tick in ticks:
        ty = y_scale(tick)
        if show_gridlines:
            children.append(Element(tag="line", attrs={
                "class": gridline_cls,
                "x1": "0", "x2": "100%",
                "y1": _fmt(ty), "y2": _fmt(ty),
            }, children=()))
        if show_axis:
            children.append(Element(tag="text", attrs={
                "class": label_cls,
                "x": "-6", "y": _fmt(ty),
                "font-size": str(axis_font),
                "text-anchor": "end",
                "dominant-baseline": "middle",
            }, children=(TextNode(format_value(tick, y_format, y_unit)),)))
    return Element(tag="g", attrs={"class": group_class},
                   children=tuple(children))


#: Room right of the plot: half of the last x label, the end of a
#: reference label.
PLOT_MARGIN_RIGHT = 12


def plot_svg(
    slot: Callable[..., str],
    children: Sequence[Element],
    *,
    height: int,
    margin_left: int,
    aria_label: str,
) -> Element:
    """The ``<svg>`` of a series chart — which IS its plot rectangle.

    It fills the wrapper less its two margins, and every horizontal
    coordinate inside is a percentage of it (:func:`~._svg._pct`): the
    chart takes the width of its container, whatever the server could
    not know about it. The margins are therefore CSS, not coordinates;
    what sits in them (the y labels, the last x label's half) is drawn
    at negative or beyond-100 % positions, which the slot's
    ``overflow-visible`` shows.

    No ``viewBox``, on purpose: it would fix the aspect ratio, so a wide
    card would letterbox the drawing. Physical ``margin-left`` and not
    ``margin-inline-start``: the drawing's coordinates are left-to-right
    whatever the document's direction, so its margin is too.
    """
    return Element(tag="svg", attrs={
        "class": slot("svg"),
        "height": str(height),
        "style": (
            f"width:calc(100% - {margin_left + PLOT_MARGIN_RIGHT}px);"
            f"margin-left:{margin_left}px"
        ),
        "role": "img",
        "aria-label": aria_label,
    }, children=tuple(children))


def apply_fixed_width(wrapper_attrs: dict[str, Any], width: int | None) -> None:
    """``width=N``: the chart is N pixels wide, never wider than its
    container. Without it, it fills the container.

    Written BEFORE the author's own ``style=`` so that one still wins.
    """
    if not width:
        return
    fixed = f"width:{int(width)}px;max-width:100%"
    existing = wrapper_attrs.get("style")
    wrapper_attrs["style"] = f"{fixed};{existing}" if existing else fixed


def render_static_legend(
    slot: Callable[..., str],
    entries: Sequence[tuple[str | None, str]],
) -> Element:
    """The non-interactive legend: one dot + one label per entry.

    ``entries`` is a sequence of ``(colour, label)`` — the series charts
    pass ``(s.color, s.name)``, the pie passes ``(palette[i], label)``.
    The interactive version (line / scatter, with series toggle) stays
    separate, it has a real behaviour.
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


def data_table(
    slot: Callable[..., str],
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    shown: bool,
) -> Element:
    """The table behind the drawing — the values a screen reader cannot
    read off a picture (the ``aria-label`` only sums it up).

    Always there: invisible (``sr-only``) by default; with ``show_data``,
    a ``<details>`` that opens a ``ui.table`` under the chart, « Voir les
    données » / « Masquer les données ». Native ``<details>``: no script,
    and the summary is a button the keyboard reaches."""
    if not shown:
        head = Element(tag="tr", attrs={}, children=tuple(
            Element(tag="th", attrs={"scope": "col"}, children=(TextNode(h),))
            for h in header))
        body = tuple(Element(tag="tr", attrs={}, children=tuple(
            Element(tag="td", attrs=localized_attr(cell), children=(TextNode(cell),))
            for cell in row))
            for row in rows)
        # ``sr-only`` on a DIV, the table inside: a ``<table>`` ignores
        # ``height`` and ``overflow``, keeps its rows' height, and would
        # hang under a card that clips.
        return Element(tag="div", attrs={"class": "sr-only"}, children=(
            Element(tag="table", attrs={}, children=(
                Element(tag="thead", attrs={}, children=(head,)),
                Element(tag="tbody", attrs={}, children=body),
            )),
        ))
    from bretzel.components.base.component import Component
    from bretzel.components.data.table.table import Table, column

    def _cell(value: Any, _row: Any) -> Any:
        # A date the browser writes in the page's language keeps its
        # twin through the table (``Localized``).
        if isinstance(value, Localized):
            return Element(tag="span", attrs=localized_attr(value), children=(TextNode(value),))
        return value

    table = Table(
        columns=[column(f"c{i}", label=h, align="left" if i == 0 else "right",
                        render=_cell)
                 for i, h in enumerate(header)],
        rows=[{"key": n, **{f"c{i}": cell for i, cell in enumerate(row)}}
              for n, row in enumerate(rows)],
        row_key="key",
    )
    Component._detach_from_parent(table)
    toggle_cls = slot("data_toggle")
    toggle = Element(tag="summary", attrs={"class": toggle_cls}, children=(
        Element(tag="span", attrs={"class": "group-open:hidden"},
                children=(TextNode(text("chart.show_data")),)),
        Element(tag="span", attrs={"class": "hidden group-open:inline"},
                children=(TextNode(text("chart.hide_data")),)),
    ))
    return Element(tag="details", attrs={"class": slot("data")},
                   children=(toggle, table.render()))


def keyboard_attrs(attrs: dict[str, Any]) -> None:
    """A chart with points is ONE tab stop: the arrows walk its points,
    Enter clicks one, Escape leaves (``keyboard()`` in ``charts.js``,
    merged into every chart scope). The ring is the wrapper's slot."""
    attrs["tabindex"] = "0"
    attrs["bz-on:keydown"] = "key($event)"
    attrs["bz-on:focusout"] = "unkey($event)"


def titled(
    slot: Callable[..., str], svg: Element, *, top: str | None, bottom: str | None,
) -> list[Element]:
    """The plot between its axis titles (``x_label`` / ``y_label``): the
    vertical axis's above it, at its left, the horizontal axis's below
    it, at its right — read level, as Observable Plot sets them, never
    turned on their side. Their font comes with the slot, from the size
    step (``size=`` moves them with the axis labels)."""
    out: list[Element] = []
    if top:
        out.append(Element(tag="div", attrs={"class": slot("title_top")},
                           children=(TextNode(top),)))
    out.append(svg)
    if bottom:
        out.append(Element(tag="div", attrs={"class": slot("title_bottom")},
                           children=(TextNode(bottom),)))
    return out


def render_line_axis_layer(
    slot, ticks: list[float], y_scale,
    axis_font: int, show_axis: bool, show_gridlines: bool, y_format,
    y_unit: str | None = None,
) -> Element:
    """The vertical axis of the charts drawing x/y points."""
    return render_axis_layer(
        slot, ticks, y_scale, axis_font,
        show_axis, show_gridlines, y_format, y_unit,
        group_class="bz-line-axes",
    )


def render_x_axis_labels(
    slot, xmin: float, xmax: float, x_scale, plot_bottom: float,
    axis_font: int, x_format, x_unit: str | None = None, *, whole_x: bool = False,
    time_axis: bool = False,
) -> Element:
    """Numeric ticks across the X domain — Heckbert ~5 ticks; by 1 at
    least when every x is whole (``whole_x``: weeks, seats, days).

    ``compute_ticks`` rounds outward to the next nice number, so for a
    raw domain like ``(0, 11)`` it returns ``[0, 5, 10, 15]`` — the
    ``15`` would land past the plot's right edge and dangle off the chart.
    Filter to the in-domain ticks so the axis stops cleanly at the
    data. Same logic applies on the date axis : timestamps past xmax
    would render past the chart.
    """
    # A time axis is graduated on round moments (``compute_time_ticks``);
    # past its last step, or on numbers, the nice numbers.
    timed = compute_time_ticks(xmin, xmax, target_count=5) if time_axis else None
    ticks = timed if timed else [
        t for t in compute_ticks(xmin, xmax, target_count=5, whole=whole_x)
        if xmin <= t <= xmax]
    label_cls = slot("axis_label")
    children: list[Element] = []
    for tick in ticks:
        label = format_value(tick, x_format, x_unit)
        children.append(Element(tag="text", attrs={
            "class": label_cls,
            "x": _pct(x_scale(tick)),
            "y": _fmt(plot_bottom + axis_font + 8),
            "font-size": str(axis_font),
            "text-anchor": "middle",
            **localized_attr(label),
        }, children=(TextNode(label),)))
    return Element(tag="g", attrs={"class": "bz-line-x-labels"},
                   children=tuple(children))


def render_toggle_legend(slot, series: list[Series]) -> Element:
    legend_attrs = {"class": slot("legend")}
    label_cls = slot("legend_label")
    item_cls = slot("legend_item")
    children: list[Element] = []
    for s_idx, s in enumerate(series):
        dot_cls = slot("legend_dot", s.color or None)
        # ``bz-on:click`` flips the visibility boolean. V3 has no
        # ``.prevent`` modifier so ``preventDefault`` is inlined ; the
        # button is ``type="button"`` so this is just belt-and-braces.
        # ``bz-class`` MERGES the dim utility onto the static
        # ``legend_item`` classes (never ``bz-attr:class``, which would
        # clobber them) — the item dims to 40 % opacity when off so the
        # user sees which series are hidden at a glance ; the dot keeps
        # full opacity so the colour swatch stays readable as a legend
        # key. All series start visible so ``opacity-100`` is the SSR
        # snapshot — no pre-stamp needed.
        children.append(Element(tag="button", attrs={
            "type": "button",
            "class": item_cls,
            "bz-on:click": (
                f"$event.preventDefault(); toggleSeries({s_idx})"
            ),
            "bz-class": (
                f"isVisible({s_idx}) ? 'opacity-100' : 'opacity-40'"
            ),
            "aria-pressed": "true",
            # Stringify — a raw boolean makes ``bz-attr`` write an empty
            # attr (true) / remove it (false) instead of the "true" /
            # "false" string aria-pressed needs (data-attr trap).
            "bz-attr:aria-pressed": bool_attr(f"isVisible({s_idx})"),
        }, children=(
            Element(tag="span", attrs={"class": dot_cls}, children=()),
            Element(tag="span", attrs={"class": label_cls},
                    children=(TextNode(s.name or text("chart.series")),)),
        )))
    return Element(tag="div", attrs=legend_attrs, children=tuple(children))


__all__ = [
    "render_line_axis_layer",
    "render_toggle_legend",
    "render_x_axis_labels",
    "PLOT_MARGIN_RIGHT",
    "apply_fixed_width",
    "data_table",
    "keyboard_attrs",
    "plot_svg",
    "render_axis_layer",
    "render_empty_state",
    "render_static_legend",
    "titled",
]
