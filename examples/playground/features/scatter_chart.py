"""``ScatterChart`` test bench.

Five cards : Reference / Edge cases / Composability / A11y / Server
playground. ``BINDABLE_PROPS = ()`` — data flows via
``@refreshable``. Per-dot hover via the shared floating tooltip ;
multi-series legend click-to-toggle.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/scatter_chart"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
Y_FORMATS = ["", "abbreviated", "percent", "currency"]


_rng = random.Random(2026)


def gauss_cluster(cx: float, cy: float, n: int, spread: float) -> list[tuple]:
    """Tiny Gaussian-ish cluster — purely for the playground demos."""
    out: list[tuple] = []
    for _ in range(n):
        out.append((cx + _rng.gauss(0, spread),
                    cy + _rng.gauss(0, spread)))
    return out


# Single-series demo — a noisy y = x + noise correlation.
SAMPLE = [
    (round(x, 2), round(x * 1.5 + 5 + _rng.gauss(0, 4), 1))
    for x in [_rng.uniform(0, 20) for _ in range(50)]
]

# Two clusters for a multi-series correlation demo.
TWO_CLUSTERS = [
    Series(name="Cohort A",
           data=[(round(x, 2), round(y, 1))
                 for x, y in gauss_cluster(5, 60, 40, 4)]),
    Series(name="Cohort B",
           data=[(round(x, 2), round(y, 1))
                 for x, y in gauss_cluster(15, 30, 40, 5)]),
]


class ScatterChartPlayground(PageState):
    color:          str  = field(default="primary")
    size:           str  = field(default="md")
    width:          int  = field(default=600)
    show_axis:      bool = field(default=True)
    show_gridlines: bool = field(default=True)
    show_legend:    bool = field(default=True)
    y_format:       str  = field(default="")
    x_format:       str  = field(default="")
    y_unit:         str  = field(default="")
    x_unit:         str  = field(default="")
    empty_text:     str  = field(default="")
    empty_icon:     str  = field(default="scatter-chart")
    empty_desc:     str  = field(default="")
    empty_escape:   bool = field(default=False)
    multi:          bool = field(default=False)
    empty:          bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: ScatterChartPlayground) -> None:
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


def build_preview(state: ScatterChartPlayground):
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
        "width": state.width,
        "show_axis": state.show_axis,
        "show_gridlines": state.show_gridlines,
        "show_legend": state.show_legend,
    }
    if state.y_format:
        kwargs["y_format"] = state.y_format
    if state.x_format:
        kwargs["x_format"] = state.x_format
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
    if state.empty:
        data = []
    else:
        data = TWO_CLUSTERS if state.multi else SAMPLE
    return ui.scatter_chart(data, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[ScatterChartPlayground])
def server_panel() -> None:
    state = ScatterChartPlayground()

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
        with control("x_format"):
            ui.select(value=state.x_format,
                      options=[(f or "(default)", f or "(default)")
                               for f in Y_FORMATS],
                      on_change=server_changed)
        with control("y_unit (suffix)"):
            ui.input(value=state.y_unit, placeholder="score",
                     on_change=server_changed)
        with control("x_unit (suffix)"):
            ui.input(value=state.x_unit, placeholder="days",
                     on_change=server_changed)
        with control("empty_text (when empty=True)"):
            ui.input(value=state.empty_text, placeholder="No data.",
                     on_change=server_changed)
        with control("empty_icon (dataset='empty')"):
            ui.input(value=state.empty_icon, placeholder="scatter-chart",
                     on_change=server_changed)
        with control("empty_description (dataset='empty')"):
            ui.input(value=state.empty_desc, placeholder='Pick a range.',
                     on_change=server_changed)
        with control("empty= (escape hatch, dataset='empty')"):
            ui.switch(checked=state.empty_escape, on_change=server_changed)
        with control("multi-cluster (2 series)"):
            ui.switch(checked=state.multi, on_change=server_changed)
        with control("empty (0 points)"):
            ui.switch(checked=state.empty, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="border rounded-xl p-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-scatter",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Correlation scatter",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("extra_attrs (one per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=scatter",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="X vs Y",
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
            ui.heading("ScatterChart", level=1)
            ui.text(
                "Continuous-X-Y scatter plot — the analysis companion "
                "to ``ui.line_chart``. Distributions, correlations, "
                "residuals. Each ``<circle>`` is a hover target ; the "
                "shared floating tooltip lands just above the point. "
                "Multi-series legend is click-to-toggle, same pattern "
                "as LineChart.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading("Sizes", level=3)
                    with ui.vstack(gap="md"):
                        for s in SIZES:
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                ui.scatter_chart(SAMPLE, size=s, width=480)

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in COLORS:
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.scatter_chart(SAMPLE, color=c, width=400,
                                                 size="sm")

                    ui.heading("Multi-cluster — click the legend",
                               level=3)
                    ui.text(
                        "Two cohorts at different locations on the "
                        "plane. Each series has its OWN x-values "
                        "(unlike LineChart, scatter doesn't require "
                        "shared x). Click a legend item to isolate "
                        "one cohort.",
                        color="muted", size="xs",
                    )
                    ui.scatter_chart(TWO_CLUSTERS, width=560, size="md")

                    ui.heading("Reference lines (thresholds)", level=3)
                    ui.text(
                        "Same ``reference_lines=`` kwarg as the rest "
                        "of the family — dashed thresholds behind the "
                        "dots with a right-edge label.",
                        color="muted", size="xs",
                    )
                    ui.scatter_chart(
                        SAMPLE, width=560, size="md",
                        reference_lines=[
                            Reference(value=20, label="Outlier band",
                                      color="warning"),
                            Reference(value=10, label="Median"),
                        ],
                    )

                    ui.heading("Date axis (auto-detect)", level=3)
                    daily = [
                        (date(2026, 1, 1) + timedelta(days=i),
                         round(50 + 20 * math.sin(i / 4.0)
                               + _rng.gauss(0, 6), 1))
                        for i in range(45)
                    ]
                    ui.scatter_chart(daily, width=560, size="md",
                                     color="info", y_unit="ms")

                    ui.heading(
                        "show_axis / show_gridlines / show_legend "
                        "/ x_format / x_unit / empty_text", level=3,
                    )
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("show_axis=False, show_gridlines"
                                    "=False", color="muted", size="xs")
                            ui.scatter_chart(SAMPLE, width=350, size="sm",
                                             show_axis=False,
                                             show_gridlines=False)
                        with ui.vstack(gap="xs"):
                            ui.text("show_legend=False (multi)",
                                    color="muted", size="xs")
                            ui.scatter_chart(TWO_CLUSTERS, width=350,
                                             size="sm", show_legend=False)
                        with ui.vstack(gap="xs"):
                            ui.text("x_format + x_unit", color="muted",
                                    size="xs")
                            ui.scatter_chart(SAMPLE, width=350, size="sm",
                                             x_format="abbreviated",
                                             x_unit="pts")
                        with ui.vstack(gap="xs"):
                            ui.text("empty_text (data=[])", color="muted",
                                    size="xs")
                            ui.scatter_chart([], width=350, size="sm",
                                             empty_text="No points yet.")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Empty data", level=3)
                    ui.scatter_chart([], width=400, size="sm")

                    ui.heading("Single point", level=3)
                    ui.scatter_chart([(5, 10)], width=400, size="sm")

                    ui.heading("Dense distribution (200 points)", level=3)
                    dense = [
                        (round(_rng.uniform(0, 100), 2),
                         round(_rng.uniform(0, 100), 2))
                        for _ in range(200)
                    ]
                    ui.scatter_chart(dense, width=560, size="md",
                                     color="primary")

                    ui.heading("Overlapping clusters", level=3)
                    overlap = [
                        Series(name="A", data=[(round(x, 2), round(y, 1))
                               for x, y in gauss_cluster(10, 50, 30, 4)]),
                        Series(name="B", data=[(round(x, 2), round(y, 1))
                               for x, y in gauss_cluster(11, 52, 30, 4)]),
                    ]
                    ui.scatter_chart(overlap, width=560, size="md")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Embedded in a KPI tile next to a headline.",
                            color="muted", size="sm")
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Response time correlation",
                                        color="muted", size="sm")
                                ui.heading("r = 0.62", level=3, size="2xl")
                                ui.scatter_chart(SAMPLE, width=320,
                                                 size="sm",
                                                 color="primary")
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Cohort comparison",
                                        color="muted", size="sm")
                                ui.scatter_chart(TWO_CLUSTERS, width=320,
                                                 size="sm")

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
                    ui.scatter_chart(data=[], empty_text='Nothing to show.',
                             empty_icon="unplug",
                             empty_description='No point to plot.')

                    ui.heading('Empty state — ``empty=`` takes over',
                               level=3)
                    ui.scatter_chart(
                        data=[],
                        empty=lambda: ui.button('Import a set',
                                                icon_left="plus",
                                                variant="soft",
                                                size="sm"))

                    ui.heading("A11y", level=2)
                    ui.text(
                        "Auto ``aria-label`` reports the point count + "
                        "series names. Override via ``attrs={\"aria-"
                        "label\": ...}`` when the surrounding context "
                        "describes the data. Keyboard hover support "
                        "lands when a concrete request arrives.",
                        color="muted", size="sm",
                    )
                    ui.scatter_chart(SAMPLE, width=480, size="sm",
                                     attrs={"aria-label":
                                            "Latency vs load, 50 points"})

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop and every escape hatch is wired. "
                        "Flip ``multi-cluster`` to swap between a "
                        "50-point regression and a 2 × 40-point cohort "
                        "comparison.",
                        color="muted", size="sm",
                    )
                    server_panel()
