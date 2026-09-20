"""``LineChart`` test bench.

Five cards : Reference / Edge cases / Composability / A11y / Server
playground. ``BINDABLE_PROPS = ()`` — data flows via
``@refreshable``. No per-point handlers in v1 ; the crosshair +
tooltip are pure client-side.
"""

from __future__ import annotations

import math

from datetime import date, datetime, timedelta

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/line_chart"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
Y_FORMATS = ["", "abbreviated", "percent", "currency"]


SAMPLE = [(i, round(50 + 20 * math.sin(i / 2.0) + i * 1.5, 1))
          for i in range(20)]

NOISY = [(i, round(40 + 30 * math.sin(i / 1.3) + (i * 7) % 11, 1))
         for i in range(30)]

SHARP = [(i, v) for i, v in enumerate(
    [10, 12, 11, 25, 27, 26, 8, 9, 7, 30, 33, 31, 12, 14, 13])]

NEGATIVE_MIX = [(i, v) for i, v in enumerate(
    [-5, 2, -3, 8, 1, -7, 4, 6, -2, 10, 5, -1])]

DUAL_SERIES = [
    Series(name="Sales",
           data=[(i, round(50 + 25 * math.sin(i / 2.5) + i * 1.8, 1))
                 for i in range(15)]),
    Series(name="Costs",
           data=[(i, round(30 + 18 * math.cos(i / 2.0) + i * 1.2, 1))
                 for i in range(15)]),
]

THREE_SERIES = [
    Series(name="Acme",   data=[(i, round(60 + 15 * math.sin(i / 1.5), 1))
                                for i in range(12)]),
    Series(name="Globex", data=[(i, round(45 + 20 * math.cos(i / 1.8), 1))
                                for i in range(12)]),
    Series(name="Initech", data=[(i, round(35 + 10 * math.sin(i / 2.2), 1))
                                 for i in range(12)]),
]


class LineChartPlayground(PageState):
    color:          str  = field(default="primary")
    size:           str  = field(default="md")
    width:          int  = field(default=600)
    # Smooth is the component default — flip to False to demo the
    # raw polyline shape (useful for step-like data).
    smooth:         bool = field(default=True)
    area_fill:      bool = field(default=False)
    show_dots:      bool = field(default=False)
    show_axis:      bool = field(default=True)
    show_gridlines: bool = field(default=True)
    show_legend:    bool = field(default=True)
    y_format:       str  = field(default="")
    y_unit:         str  = field(default="")
    x_unit:         str  = field(default="")
    empty_text:     str  = field(default="")
    empty_icon:     str  = field(default="line-chart")
    empty_desc:     str  = field(default="")
    empty_escape:   bool = field(default=False)
    dataset:        str  = field(default="sample")
    multi:          bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: LineChartPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def dataset(state: LineChartPlayground):
    if state.multi:
        return DUAL_SERIES
    return {
        "sample":   SAMPLE,
        "noisy":    NOISY,
        "sharp":    SHARP,
        "negative": NEGATIVE_MIX,
        "empty":    [],
    }.get(state.dataset, SAMPLE)


def build_preview(state: LineChartPlayground):
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
        "width": state.width,
        "smooth": state.smooth,
        "area_fill": state.area_fill,
        "show_dots": state.show_dots,
        "show_axis": state.show_axis,
        "show_gridlines": state.show_gridlines,
        "show_legend": state.show_legend,
    }
    if state.y_format:
        kwargs["y_format"] = state.y_format
    if state.y_unit:
        kwargs["y_unit"] = state.y_unit
    if state.x_unit:
        kwargs["x_unit"] = state.x_unit
    if state.empty_text:
        kwargs["empty_text"] = state.empty_text
    if state.empty_icon:
        kwargs["empty_icon"] = state.empty_icon
    if state.empty_desc:
        kwargs["empty_description"] = state.empty_desc
    if state.empty_escape:
        # The escape hatch: the author puts what they want in place
        # of the automatic empty state — the same contract as
        # ``ui.table`` / ``ui.diagram``.
        kwargs["empty"] = lambda: ui.button(
            'Import a data set', variant="soft", size="sm")
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.line_chart(dataset(state), **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[LineChartPlayground])
def server_panel() -> None:
    state = LineChartPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("width (px)"):
            ui.number_input(value=state.width, min=200, max=1200, step=40,
                            on_change=server_changed)
        with control("smooth"):
            ui.switch(checked=state.smooth, on_change=server_changed)
        with control("area_fill"):
            ui.switch(checked=state.area_fill, on_change=server_changed)
        with control("show_dots"):
            ui.switch(checked=state.show_dots, on_change=server_changed)
        with control("show_axis"):
            ui.switch(checked=state.show_axis, on_change=server_changed)
        with control("show_gridlines"):
            ui.switch(checked=state.show_gridlines, on_change=server_changed)
        with control("show_legend"):
            ui.switch(checked=state.show_legend, on_change=server_changed)
        with control("y_format"):
            ui.select(value=state.y_format,
                      options=[(f or "(default)", f or "(default)")
                               for f in Y_FORMATS],
                      on_change=server_changed)
        with control("y_unit"):
            ui.input(value=state.y_unit,
                     placeholder="ms / users / req",
                     on_change=server_changed)
        with control("x_unit"):
            ui.input(value=state.x_unit,
                     placeholder="day / hour",
                     on_change=server_changed)
        with control("empty_text (dataset='empty')"):
            ui.input(value=state.empty_text, placeholder="No data.",
                     on_change=server_changed)
        with control("empty_icon (dataset='empty')"):
            ui.input(value=state.empty_icon, placeholder="line-chart",
                     on_change=server_changed)
        with control("empty_description (dataset='empty')"):
            ui.input(value=state.empty_desc, placeholder='Pick a range.',
                     on_change=server_changed)
        with control("empty= (escape hatch, dataset='empty')"):
            ui.switch(checked=state.empty_escape, on_change=server_changed)
        with control("dataset (single-series)"):
            ui.select(value=state.dataset,
                      options=[("sample",   "smooth wave (20 pts)"),
                               ("noisy",    "noisy (30 pts)"),
                               ("sharp",    "sharp jumps (15 pts)"),
                               ("negative", "mixed +/- (12 pts)"),
                               ("empty",    "empty (0 pts)")],
                      on_change=server_changed)
        with control("multi-series (2 × 15 pts)"):
            ui.switch(checked=state.multi, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="border rounded-xl p-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-line",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Daily activity",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("extra_attrs (one per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=line",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Hover for details",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("LineChart", level=1)
            ui.text(
                "Continuous-x line chart, smooth by default. Hover "
                "behaviour is **hybrid** : single-series uses the "
                "shared floating tooltip on per-point invisible "
                "``<circle>`` hover targets (same recipe scatter / "
                "bar / pie use — tight bbox, the browser does all the "
                "screen-coord work). Multi-series uses an inline "
                "panel anchored ``top-3 right-3`` of the chart that "
                "shows the vertical breakdown (``x = N / A: ... / B: "
                "...``) — a multi-series killer feature the per-point "
                "tooltip can't match. Click a legend item to toggle "
                "that series ; the last visible series can't be "
                "hidden.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan across the main axes.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.vstack(gap="md"):
                        for s in SIZES:
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                ui.line_chart(SAMPLE, size=s, width=480)

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in COLORS:
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.line_chart(SAMPLE, color=c, width=400,
                                              size="sm")

                    ui.heading("Variants", level=3)
                    ui.text(
                        "Defaults : smooth, no area fill, no dots. The "
                        "Sizes + Colors rows above already exercise the "
                        "baseline ; these tiles show how each opt-in "
                        "deviates.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for label, kwargs in (
                            ("smooth=False (sharp polyline)",
                             {"smooth": False}),
                            ("area_fill",
                             {"area_fill": True}),
                            ("show_dots",
                             {"show_dots": True}),
                            ("area_fill + show_dots",
                             {"area_fill": True, "show_dots": True}),
                            ("smooth=False + show_dots",
                             {"smooth": False, "show_dots": True}),
                        ):
                            with ui.vstack(gap="xs"):
                                ui.text(label, color="muted", size="xs")
                                ui.line_chart(SAMPLE, width=400, size="sm",
                                              **kwargs)

                    ui.heading("Hover UX — single vs multi-series",
                               level=3)
                    ui.text(
                        "Single-series : hover any point on the curve "
                        "to see the floating tooltip just above it ; "
                        "the dot fades in coloured at your cursor's "
                        "position. Multi-series : panel top-right with "
                        "the vertical breakdown. Same data shape, "
                        "different UX — the framework picks the "
                        "right one.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("single-series (floating)",
                                    color="muted", size="xs")
                            ui.line_chart(SAMPLE, width=400, size="sm")
                        with ui.vstack(gap="xs"):
                            ui.text("multi-series (panel)",
                                    color="muted", size="xs")
                            ui.line_chart(THREE_SERIES, width=400,
                                          size="sm")

                    ui.heading("Multi-series — click the legend", level=3)
                    ui.text(
                        "Click any legend item to hide that series ; "
                        "click again to bring it back. Pure client-side on "
                        "the client (Vercel / Stripe pattern). The "
                        "guard prevents hiding the last visible "
                        "series — an empty chart reads as broken.",
                        color="muted", size="xs",
                    )
                    ui.line_chart(THREE_SERIES, width=560, size="md")

                    ui.heading("Reference lines (thresholds + goals)",
                               level=3)
                    ui.text(
                        "``reference_lines=[Reference(value=N, label=\"...\", "
                        "color=\"...\")]`` (or bare ``(value, label)`` "
                        "/ ``(value, label, color)`` tuples) draws "
                        "dashed thresholds behind the data with a "
                        "right-edge label. ``color=None`` falls back "
                        "to muted so the line stays out of the way.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Single goal", color="muted", size="xs")
                            ui.line_chart(
                                SAMPLE, width=400, size="sm",
                                reference_lines=[
                                    Reference(value=75, label="Q3 goal",
                                              color="success"),
                                ],
                            )
                        with ui.vstack(gap="xs"):
                            ui.text("Multi-band", color="muted", size="xs")
                            ui.line_chart(
                                SAMPLE, width=400, size="sm",
                                reference_lines=[
                                    Reference(60, "Floor"),
                                    Reference(80, "Target", "warning"),
                                    Reference(95, "Stretch", "success"),
                                ],
                            )

                    ui.heading("Date axis (auto-detect)", level=3)
                    ui.text(
                        "Pass ``date`` / ``datetime`` x values direct ; "
                        "the chart picks an x-format from the visible "
                        "span (``HH:MM`` < 1 day → ``Mon DD`` < 1 year "
                        "→ ``Mon YYYY`` < 5 years → ``YYYY`` beyond). "
                        "``x_format=callable`` overrides the auto-pick.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Hourly (24h)",
                                    color="muted", size="xs")
                            hourly = [
                                (datetime(2026, 6, 1, h, 0),
                                 round(40 + 30 * math.sin(h / 4.0)
                                       + h * 0.5, 1))
                                for h in range(24)
                            ]
                            ui.line_chart(hourly, width=400, size="sm",
                                          y_unit="ms")
                            # ``x_format=`` takes over from the
                            # automatic choice — the sentence above has
                            # announced it forever, nobody passed it.
                            ui.text('...with x_format=callable',
                                    color="muted", size="xs")
                            ui.line_chart(
                                hourly, width=400, size="sm", y_unit="ms",
                                x_format=lambda d: f"{d.hour:02d}h")
                        with ui.vstack(gap="xs"):
                            ui.text("Daily (30 days)",
                                    color="muted", size="xs")
                            daily = [
                                (date(2026, 6, 1) + timedelta(days=i),
                                 round(50 + 25 * math.sin(i / 4.0)
                                       + i * 0.7, 1))
                                for i in range(30)
                            ]
                            ui.line_chart(daily, width=400, size="sm",
                                          area_fill=True)
                        with ui.vstack(gap="xs"):
                            ui.text("Monthly (24 months)",
                                    color="muted", size="xs")
                            monthly = [
                                (date(2024, 1, 1) + timedelta(days=30 * i),
                                 round(100 + 50 * math.sin(i / 6.0)
                                       + i * 2.5, 1))
                                for i in range(24)
                            ]
                            ui.line_chart(monthly, width=400, size="sm",
                                          y_format="abbreviated")
                        with ui.vstack(gap="xs"):
                            ui.text("Yearly (8 years)",
                                    color="muted", size="xs")
                            yearly = [
                                (date(2020 + i, 6, 1),
                                 round(200 + 80 * math.sin(i / 2.0)
                                       + i * 30, 1))
                                for i in range(8)
                            ]
                            ui.line_chart(yearly, width=400, size="sm",
                                          y_format="abbreviated",
                                          y_unit="users")

                    ui.heading("With units (y_unit / x_unit)", level=3)
                    ui.text(
                        "Suffix any number — ``y_format='abbreviated', "
                        "y_unit='users'`` → ``1.5k users``. The unit "
                        "lands on the axis ticks AND inside the "
                        "tooltip.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("y_unit=\"ms\"", color="muted",
                                    size="xs")
                            ui.line_chart(SAMPLE, width=400, size="sm",
                                          y_unit="ms")
                        with ui.vstack(gap="xs"):
                            ui.text("y_format=\"abbreviated\" + "
                                    "y_unit=\"users\"",
                                    color="muted", size="xs")
                            big = [(x, y * 100) for x, y in SAMPLE]
                            ui.line_chart(big, width=400, size="sm",
                                          y_format="abbreviated",
                                          y_unit="users")
                        with ui.vstack(gap="xs"):
                            ui.text("x_unit=\"s\" + y_unit=\"ms\"",
                                    color="muted", size="xs")
                            ui.line_chart(SAMPLE, width=400, size="sm",
                                          x_unit="s", y_unit="ms")
                        with ui.vstack(gap="xs"):
                            ui.text("x_unit=\"h\" (hour-of-day axis)",
                                    color="muted", size="xs")
                            hourly = [(h, round(20 + 40 * (1 - abs(h - 12) / 12), 1))
                                      for h in range(24)]
                            ui.line_chart(hourly, width=400, size="sm",
                                          x_unit="h",
                                          y_format="abbreviated",
                                          y_unit="req/s")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Empty data", level=3)
                    ui.line_chart([], width=400, size="sm")

                    ui.heading("Single point", level=3)
                    ui.line_chart([(0, 42)], show_dots=True,
                                  width=400, size="sm")

                    ui.heading("Two points (straight segment)", level=3)
                    ui.line_chart([(0, 5), (10, 15)], width=400, size="sm",
                                  show_dots=True)

                    ui.heading("Flat series (zero variance)", level=3)
                    ui.line_chart([(i, 5) for i in range(8)],
                                  width=400, size="sm")

                    ui.heading("Mixed positive / negative", level=3)
                    ui.line_chart(NEGATIVE_MIX, area_fill=True,
                                  width=400, size="sm")

                    ui.heading("Dense series (100 points)", level=3)
                    dense = [(i, round(50 + 30 * math.sin(i / 4.0)
                                       + (i * 7) % 11, 1))
                             for i in range(100)]
                    ui.line_chart(dense, smooth=True, width=560, size="md")

                    ui.heading("list[number] shortcut (x = index)", level=3)
                    ui.line_chart([5, 8, 3, 12, 6, 14, 9],
                                  show_dots=True, width=400, size="sm")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Embedded in KPI cards + a dual-series "
                            "comparison tile.",
                            color="muted", size="sm")

                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Sessions", color="muted",
                                        size="sm")
                                ui.heading("12 944", level=3, size="2xl")
                                ui.line_chart(SAMPLE, color="primary",
                                              smooth=True, area_fill=True,
                                              show_axis=False,
                                              show_gridlines=False,
                                              size="sm", width=320)
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Sales vs costs", color="muted",
                                        size="sm")
                                ui.line_chart(DUAL_SERIES, smooth=True,
                                              size="sm", width=320)

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading('Empty state — the three props and the escape hatch',
                               level=3)
                    ui.text('The four charts only offered ``empty_text`` where '
                        'table, datatable and diagram offered all four. They '
                        'have composed the same ``ui.empty_state`` since '
                        '2026-09-07.',
                            color="muted", size="xs")
                    ui.line_chart(data=[], empty_text='Nothing to show.',
                             empty_icon="unplug",
                             empty_description='No measurement over the range.')

                    ui.heading('Empty state — ``empty=`` takes over',
                               level=3)
                    ui.line_chart(
                        data=[],
                        empty=lambda: ui.button('Import a set',
                                                icon_left="plus",
                                                variant="soft",
                                                size="sm"))

                    ui.heading("A11y", level=2)
                    ui.text(
                        "Charts emit ``role=\"img\"`` with an auto-"
                        "generated ``aria-label`` summarising the point "
                        "count and (multi-series) the series names. "
                        "Override via ``attrs={\"aria-label\": ...}`` "
                        "when the surrounding text already describes "
                        "the data. The crosshair is mouse-driven only "
                        "in v1 ; keyboard hover support lands when a "
                        "concrete request arrives.",
                        color="muted", size="sm",
                    )
                    ui.line_chart(SAMPLE, width=480, size="sm",
                                  attrs={"aria-label":
                                         "Weekly active users, 20 buckets"})

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop and every escape hatch is wired. "
                        "Flip ``multi-series`` to swap into the 2-line "
                        "dataset ; the tooltip then summarises both "
                        "values at the active x.",
                        color="muted", size="sm",
                    )
                    server_panel()
