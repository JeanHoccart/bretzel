"""``BarChart`` test bench.

Six cards : Reference / Edge cases / Composability / A11y / Server
playground / Server events. ``BINDABLE_PROPS = ()`` — data flows via
``@refreshable``. Per-bar ``on_item_click(label, value)`` registers a
distinct signed token per ``<rect>`` ; the Server events card logs
them.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/bar_chart"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
Y_FORMATS = ["", "abbreviated", "percent", "currency"]


SAMPLE = [
    ("Jan", 12), ("Feb", 18), ("Mar", 7),
    ("Apr", 21), ("May", 15), ("Jun", 24),
]

LONG_LABELS = [
    ("Monday", 8), ("Tuesday", 14), ("Wednesday", 11),
    ("Thursday", 19), ("Friday", 22), ("Saturday", 6), ("Sunday", 4),
]

NEGATIVE_MIX = [
    ("Q1", 5), ("Q2", -3), ("Q3", 8), ("Q4", -1),
]

PERCENT_MIX = [
    ("Direct", 0.42), ("Search", 0.28), ("Social", 0.18), ("Email", 0.12),
]

QUARTERLY_MULTI = [
    Series(name="2023", data=[("Q1", 12), ("Q2", 15), ("Q3", 10), ("Q4", 18)]),
    Series(name="2024", data=[("Q1", 14), ("Q2", 19), ("Q3", 13), ("Q4", 22)]),
    Series(name="2025", data=[("Q1", 16), ("Q2", 21), ("Q3", 17), ("Q4", 26)]),
]


class BarChartClientEvents(ClientState, persist="memory"):
    """The Client events card's log — on the browser side."""

    log: list = field(default_factory=list)


class BarChartPlayground(PageState):
    color:          str  = field(default="primary")
    size:           str  = field(default="md")
    width:          int  = field(default=600)
    show_values:    bool = field(default=False)
    show_axis:      bool = field(default=True)
    show_gridlines: bool = field(default=True)
    show_legend:    bool = field(default=True)
    y_format:       str  = field(default="")
    y_unit:         str  = field(default="")
    empty_text:     str  = field(default="")
    empty_icon:     str  = field(default="bar-chart-3")
    empty_desc:     str  = field(default="")
    empty_escape:   bool = field(default=False)
    dataset:        str  = field(default="months")
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


class BarChartEvents(PageState):
    log: list = field(default_factory=list)


def server_changed(state: BarChartPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def log_click(label: str, value: float) -> None:
    state = BarChartEvents()
    state.log = ([f"click → {label} = {value}"] + state.log)[:10]


def clear_log() -> None:
    state = BarChartEvents()
    state.log = []


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def dataset(state: BarChartPlayground):
    if state.multi:
        return QUARTERLY_MULTI
    return {
        "months":   SAMPLE,
        "weekdays": LONG_LABELS,
        "mixed":    NEGATIVE_MIX,
        "percent":  PERCENT_MIX,
        "empty":    [],
    }.get(state.dataset, SAMPLE)


def build_preview(state: BarChartPlayground):
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
        "width": state.width,
        "show_values": state.show_values,
        "show_axis": state.show_axis,
        "show_gridlines": state.show_gridlines,
        "show_legend": state.show_legend,
    }
    if state.y_format:
        kwargs["y_format"] = state.y_format
    if state.y_unit:
        kwargs["y_unit"] = state.y_unit
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
    return ui.bar_chart(dataset(state), **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[BarChartPlayground])
def server_panel() -> None:
    state = BarChartPlayground()

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
        with control("show_values"):
            ui.switch(checked=state.show_values, on_change=server_changed)
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
        with control("y_unit (suffix)"):
            ui.input(value=state.y_unit, placeholder="units",
                     on_change=server_changed)
        with control("empty_text (dataset='empty')"):
            ui.input(value=state.empty_text, placeholder="No data.",
                     on_change=server_changed)
        with control("empty_icon (dataset='empty')"):
            ui.input(value=state.empty_icon, placeholder="bar-chart-3",
                     on_change=server_changed)
        with control("empty_description (dataset='empty')"):
            ui.input(value=state.empty_desc, placeholder='Pick a range.',
                     on_change=server_changed)
        with control("empty= (escape hatch, dataset='empty')"):
            ui.switch(checked=state.empty_escape, on_change=server_changed)
        with control("dataset (single-series)"):
            ui.select(value=state.dataset,
                      options=[("months",   "months (6 cats)"),
                               ("weekdays", "weekdays (7 cats)"),
                               ("mixed",    "mixed +/- values"),
                               ("percent",  "percent shares"),
                               ("empty",    "empty (0 cats)")],
                      on_change=server_changed)
        with control("multi-series (3 × 4 cats)"):
            ui.switch(checked=state.multi, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="border rounded-xl p-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-bar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Revenue by month",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("extra_attrs (one per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=bar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Monthly breakdown",
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


@refreshable(deps=[BarChartEvents])
def events_panel() -> None:
    state = BarChartEvents()

    with ui.vstack():
        ui.text(
            "Click on a bar in the chart below — each ``<rect>`` carries "
            "its own HMAC-signed action token (label + value bound via "
            "``functools.partial``).",
            color="muted", size="sm",
        )
        with ui.flex(justify="center"):
            ui.bar_chart(SAMPLE, on_item_click=log_click,
                         show_values=True, color="primary")
        ui.divider()
        with ui.hstack(justify="between", align="center"):
            ui.text("Server log (latest 10)", color="muted", size="xs")
            ui.button("Clear", variant="ghost", size="xs",
                      on_click=clear_log)
        if not state.log:
            ui.text("No clicks yet.", color="muted", size="sm")
        for entry in state.log:
            ui.text(entry, size="sm")

        ui.divider()
        emitted_html_block(
            "Emitted HTML (representative — the first bar)",
            serialize_html(
                ui.bar_chart([("Jan", 12)], on_item_click=log_click),
            ),
        )


def client_events_panel() -> None:
    """The SAME event, wired onto a client expression.

    No ``@refreshable``: that is the point. The log lives in a
    ``ClientState``, the text is re-evaluated in the browser, no request
    leaves.

    WARNING: this card did not exist before 2026-09-06, and the reason
    was mechanical. ``EVENTS`` was empty, so the template read "this
    component has no event" — although the page already carried its
    Server events card. The ClassVar was wrong, not the component. Cf.
    ``.claude/work/audit-declaration-2026-09-06.md``.
    """
    events = BarChartClientEvents()
    ui.text(
        '``on_item_click`` wired to a client expression that pushes onto '
            'a ClientState. Zero requests.',
        color="muted", size="sm",
    )
    clicked = ClientExpression("String($event.detail ?? 'click')")
    ui.bar_chart(data=[("Q1", 12), ("Q2", 18), ("Q3", 9)],
                 on_item_click=events.log.push(clicked))

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-reactif — aucun rafraichissement)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    log_text = ClientExpression(
        "($bz.state.BarChartClientEvents.default.log || []).join('\\n') ||"
            " '(no events yet — click the demo above)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (click client)",
        serialize_html(ui.bar_chart(data=[("Q1", 12)],
                          on_item_click=events.log.push(clicked))),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("BarChart", level=1)
            ui.text(
                "Categorical bars, single or multi-series (grouped). "
                "Vertical orientation in v1. Hover a bar — the tooltip "
                "is drawn by ``$bz.charts.tooltipScope()`` (runtime slab "
                "``15_charts.js``) reading ``data-bz-display`` off the "
                "rect.",
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
                                ui.bar_chart(SAMPLE, size=s, width=480)

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in COLORS:
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.bar_chart(SAMPLE, color=c, width=400,
                                             size="sm")

                    ui.heading("Variants matrix : orientation × variant",
                               level=3)
                    ui.text(
                        "``orientation=\"vertical\"`` (default) puts "
                        "categories on the X axis ; ``\"horizontal\"`` "
                        "swaps them onto the Y axis (rows). "
                        "``variant=\"grouped\"`` (default) places "
                        "sub-bars side-by-side ; ``\"stacked\"`` "
                        "stacks segments along the value axis ; "
                        "``\"stacked_100\"`` normalises each category "
                        "to 100 %% for composition comparison. "
                        "Single-series payloads ignore the variant.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("vertical × grouped (default)",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm")
                        with ui.vstack(gap="xs"):
                            ui.text("vertical × stacked",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm", variant="stacked",
                                         show_values=True)
                        with ui.vstack(gap="xs"):
                            ui.text("vertical × stacked_100",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm",
                                         variant="stacked_100")
                        with ui.vstack(gap="xs"):
                            ui.text("horizontal × grouped",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm",
                                         orientation="horizontal")
                        with ui.vstack(gap="xs"):
                            ui.text("horizontal × stacked",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm",
                                         orientation="horizontal",
                                         variant="stacked",
                                         show_values=True)
                        with ui.vstack(gap="xs"):
                            ui.text("horizontal × stacked_100",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=400,
                                         size="sm",
                                         orientation="horizontal",
                                         variant="stacked_100")

                    ui.heading("Top-N ranking (horizontal grouped)",
                               level=3)
                    ui.text(
                        "Horizontal mode shines on rankings with "
                        "long category labels — Stripe / Vercel / "
                        "Linear all use it for \"top customers\", "
                        "\"top pages\", \"top errors\".",
                        color="muted", size="xs",
                    )
                    top_n = [
                        ("Customer Acquisition Cost", 412),
                        ("Lifetime Value", 1847),
                        ("Monthly Recurring Revenue", 8923),
                        ("Trial-to-Paid Conversion", 234),
                        ("Net Promoter Score", 67),
                        ("Churn Rate", 92),
                    ]
                    ui.bar_chart(top_n, width=600, size="md",
                                 orientation="horizontal",
                                 show_values=True,
                                 color="primary")

                    ui.heading("Reference lines (thresholds + goals)",
                               level=3)
                    ui.text(
                        "Same ``reference_lines=`` kwarg as LineChart "
                        "— pass ``Reference(value=..., label=..., "
                        "color=...)`` or bare tuples. The line sits "
                        "behind the bars at ``y_scale(value)`` ; the "
                        "right-edge label includes the numeric "
                        "context in parens.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("Sales target", color="muted",
                                    size="xs")
                            ui.bar_chart(
                                SAMPLE, width=400, size="sm",
                                show_values=True,
                                reference_lines=[
                                    Reference(value=15, label="Goal",
                                              color="success"),
                                ],
                            )
                        with ui.vstack(gap="xs"):
                            ui.text("Multi-band", color="muted",
                                    size="xs")
                            ui.bar_chart(
                                SAMPLE, width=400, size="sm",
                                reference_lines=[
                                    Reference(10, "Floor"),
                                    Reference(20, "Stretch", "warning"),
                                ],
                            )

                    ui.heading("show_legend / y_unit / empty_text",
                               level=3)
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("show_legend=False (multi-series)",
                                    color="muted", size="xs")
                            ui.bar_chart(QUARTERLY_MULTI, width=350,
                                         size="sm", show_legend=False)
                        with ui.vstack(gap="xs"):
                            ui.text("y_unit suffix", color="muted",
                                    size="xs")
                            ui.bar_chart(SAMPLE, width=350, size="sm",
                                         y_unit="users", show_values=True)
                        with ui.vstack(gap="xs"):
                            ui.text("empty_text (data=[])", color="muted",
                                    size="xs")
                            ui.bar_chart([], width=350, size="sm",
                                         empty_text="No sales yet.")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Empty data", level=3)
                    ui.bar_chart([], width=400, size="sm")

                    ui.heading("Single bar", level=3)
                    ui.bar_chart([("Only", 42)], width=400, size="sm",
                                 show_values=True)

                    ui.heading("All-negative values", level=3)
                    ui.bar_chart([("A", -3), ("B", -7), ("C", -2)],
                                 width=400, size="sm")

                    ui.heading("Mixed positive / negative", level=3)
                    ui.bar_chart(NEGATIVE_MIX, width=400, size="sm",
                                 show_values=True)

                    ui.heading("Very long labels", level=3)
                    ui.text("Labels overlap at this width — bump "
                            "``width`` or shorten the labels for a real "
                            "use case.",
                            color="muted", size="xs")
                    ui.bar_chart(LONG_LABELS, width=400, size="sm")

                    ui.heading("Without axis / gridlines", level=3)
                    ui.bar_chart(SAMPLE, show_axis=False,
                                 show_gridlines=False, width=400,
                                 size="sm")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Inside a Card with a heading + KPI, plus a "
                            "multi-series compact dashboard tile.",
                            color="muted", size="sm")

                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Revenue", color="muted", size="sm")
                                ui.heading("$48.3k", level=3, size="2xl")
                                ui.bar_chart(SAMPLE,
                                             color="success",
                                             y_format="currency",
                                             show_axis=False,
                                             show_gridlines=False,
                                             size="sm", width=320)
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Quarterly trend", color="muted",
                                        size="sm")
                                ui.bar_chart(QUARTERLY_MULTI,
                                             size="sm", width=320,
                                             show_axis=True)

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
                    ui.bar_chart(data=[], empty_text='Nothing to show.',
                             empty_icon="unplug",
                             empty_description='No sale over the range.')

                    ui.heading('Empty state — ``empty=`` takes over',
                               level=3)
                    ui.bar_chart(
                        data=[],
                        empty=lambda: ui.button('Import a set',
                                                icon_left="plus",
                                                variant="soft",
                                                size="sm"))

                    ui.heading("A11y", level=2)
                    ui.text(
                        "Charts emit ``role=\"img\"`` with an "
                        "auto-generated ``aria-label`` summarising the "
                        "category count and (for multi-series) the "
                        "series names. Override via ``attrs={\"aria-"
                        "label\": ...}`` when the surrounding context "
                        "already describes the data.",
                        color="muted", size="sm",
                    )
                    ui.bar_chart(SAMPLE, width=480, size="sm",
                                 attrs={"aria-label":
                                        "Monthly revenue, Jan to Jun"})

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop and every escape hatch is wired to "
                        "a control. The Emitted HTML refreshes on every "
                        "change ; flip ``multi-series`` to swap into "
                        "the 3 × 4 quarterly dataset.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # -- Client events --------------------------------------
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    client_events_panel()
