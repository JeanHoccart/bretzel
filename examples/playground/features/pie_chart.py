"""``PieChart`` test bench.

Six cards : Reference / Edge cases / Composability / A11y / Server
playground / Server events. ``BINDABLE_PROPS = ()`` — data flows via
``@refreshable``. Per-slice ``on_item_click(label, value)`` registers
distinct signed tokens per ``<path>``.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/pie_chart"


SIZES = ["xs", "sm", "md", "lg", "xl"]


SAMPLE = [
    ("Direct",  42),
    ("Search",  28),
    ("Social",  18),
    ("Email",   12),
]

UNEVEN = [
    ("Acme",    65),
    ("Globex",  20),
    ("Initech", 10),
    ("Soylent",  5),
]

LONG_TAIL = [
    ("Tier 1",  82),
    ("Tier 2",   9),
    ("Tier 3",   5),
    ("Tier 4",   2),
    ("Tier 5",   1),
    ("Tier 6", 0.5),
]


class PieChartClientEvents(ClientState, persist="memory"):
    """The Client events card's log — on the browser side."""

    log: list = field(default_factory=list)


class PieChartPlayground(PageState):
    size:         str  = field(default="md")
    variant:      str  = field(default="pie")
    show_labels:  bool = field(default=False)
    show_legend:  bool = field(default=True)
    center_text:  str  = field(default="")
    dataset:      str  = field(default="sample")
    value_format: str  = field(default="")
    value_unit:   str  = field(default="")
    empty_text:   str  = field(default="")
    empty_icon:     str  = field(default="pie-chart")
    empty_desc:     str  = field(default="")
    empty_escape:   bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class PieChartEvents(PageState):
    log: list = field(default_factory=list)


def server_changed(state: PieChartPlayground) -> None:
    # Typed param : the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted). No ``**kwargs`` / ``setattr``.
    pass


def log_click(label: str, value: float) -> None:
    state = PieChartEvents()
    state.log = ([f"slice → {label} ({value})"] + state.log)[:10]


def clear_log() -> None:
    state = PieChartEvents()
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


def dataset(state: PieChartPlayground):
    return {
        "sample":    SAMPLE,
        "uneven":    UNEVEN,
        "long_tail": LONG_TAIL,
        "empty":     [],
    }.get(state.dataset, SAMPLE)


def build_preview(state: PieChartPlayground):
    kwargs: dict = {
        "size": state.size,
        "variant": state.variant,
        "show_labels": state.show_labels,
        "show_legend": state.show_legend,
    }
    if state.center_text:
        kwargs["center_text"] = state.center_text
    if state.value_format:
        kwargs["value_format"] = state.value_format
    if state.value_unit:
        kwargs["value_unit"] = state.value_unit
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
    return ui.pie_chart(dataset(state), **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[PieChartPlayground])
def server_panel() -> None:
    state = PieChartPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant,
                      options=[("pie", "pie"), ("donut", "donut")],
                      on_change=server_changed)
        with control("show_labels"):
            ui.switch(checked=state.show_labels,
                      on_change=server_changed)
        with control("show_legend"):
            ui.switch(checked=state.show_legend,
                      on_change=server_changed)
        with control("center_text (donut only)"):
            ui.input(value=state.center_text, placeholder="100%",
                     on_change=server_changed)
        with control("value_format"):
            ui.select(value=state.value_format,
                      options=[("(default)", "(default)"),
                               ("abbreviated", "abbreviated"),
                               ("percent", "percent"),
                               ("currency", "currency")],
                      on_change=server_changed)
        with control("value_unit (suffix)"):
            ui.input(value=state.value_unit, placeholder="users",
                     on_change=server_changed)
        with control("empty_text (dataset='empty')"):
            ui.input(value=state.empty_text, placeholder="No data.",
                     on_change=server_changed)
        with control("empty_icon (dataset='empty')"):
            ui.input(value=state.empty_icon, placeholder="pie-chart",
                     on_change=server_changed)
        with control("empty_description (dataset='empty')"):
            ui.input(value=state.empty_desc, placeholder='Pick a range.',
                     on_change=server_changed)
        with control("empty= (escape hatch, dataset='empty')"):
            ui.switch(checked=state.empty_escape, on_change=server_changed)
        with control("dataset"):
            ui.select(value=state.dataset,
                      options=[("sample",    "even 4 slices"),
                               ("uneven",    "skewed 4 slices"),
                               ("long_tail", "long tail 6 slices"),
                               ("empty",     "empty (0 slices)")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="border rounded-xl p-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-pie",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Traffic share",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("extra_attrs (one per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=pie",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="By channel",
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


@refreshable(deps=[PieChartEvents])
def events_panel() -> None:
    state = PieChartEvents()
    with ui.vstack():
        ui.text(
            "Click a slice — each ``<path>`` carries its own "
            "HMAC-signed action token via ``functools.partial``.",
            color="muted", size="sm",
        )
        with ui.flex(justify="center"):
            ui.pie_chart(SAMPLE, on_item_click=log_click,
                         variant="donut", center_text="100%",
                         show_labels=True)
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
            "Emitted HTML (representative — a 2-slice pie)",
            serialize_html(
                ui.pie_chart([("A", 60), ("B", 40)],
                             on_item_click=log_click),
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
    events = PieChartClientEvents()
    ui.text(
        '``on_item_click`` wired to a client expression that pushes onto '
            'a ClientState. Zero requests.',
        color="muted", size="sm",
    )
    clicked = ClientExpression("String($event.detail ?? 'click')")
    ui.pie_chart(data=[("Chrome", 62), ("Safari", 21)],
                 on_item_click=events.log.push(clicked))

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-reactif — aucun rafraichissement)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=events.log.clear())
    log_text = ClientExpression(
        "($bz.state.PieChartClientEvents.default.log || []).join('\\n') ||"
            " '(no events yet — click the demo above)'"
    )
    ui.text(log_text, color="muted", size="sm",
            classes="font-mono whitespace-pre")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (click client)",
        serialize_html(ui.pie_chart(data=[("Chrome", 62)],
                          on_item_click=events.log.push(clicked))),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("PieChart", level=1)
            ui.text(
                "Pie or donut, optional in-chart percent labels + "
                "centre text. Per-slice hover via "
                "``$bz.charts.tooltipScope()`` ; per-slice "
                "``on_item_click(label, value)`` registers a HMAC-signed "
                "partial.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Pie vs donut, sizes, label / centre text "
                            "options.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="center", gap="lg", wrap=True):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="center"):
                                ui.pie_chart(SAMPLE, size=s)
                                ui.text(s, color="muted", size="xs")

                    ui.heading("Pie vs donut", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.pie_chart(SAMPLE, size="md")
                            ui.text("pie", color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.pie_chart(SAMPLE, size="md", variant="donut",
                                         center_text="100%")
                            ui.text("donut + center_text",
                                    color="muted", size="xs")

                    ui.heading("show_labels (% baked on arcs)", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.pie_chart(SAMPLE, size="md", show_labels=True)
                        ui.pie_chart(SAMPLE, size="md", variant="donut",
                                     show_labels=True,
                                     center_text="$48k")

                    ui.heading(
                        "show_legend / value_format / value_unit / "
                        "empty_text", level=3,
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs", align="center"):
                            ui.pie_chart(SAMPLE, size="sm",
                                         show_legend=False)
                            ui.text("show_legend=False", color="muted",
                                    size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.pie_chart(SAMPLE, size="sm",
                                         value_format="currency",
                                         value_unit="USD")
                            ui.text("value_format='currency' + "
                                    "value_unit='USD'",
                                    color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.pie_chart([], size="sm",
                                         empty_text="No sales yet.")
                            ui.text("empty_text (data=[])", color="muted",
                                    size="xs")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Empty data", level=3)
                    ui.pie_chart([], size="sm")

                    ui.heading("Single slice (full circle)", level=3)
                    ui.pie_chart([("Only", 100)], size="sm",
                                 show_labels=True)

                    ui.heading("Skewed (one dominant slice)", level=3)
                    ui.pie_chart(UNEVEN, size="md", show_labels=True)

                    ui.heading("Long tail (tiny slivers skip labels)",
                               level=3)
                    ui.pie_chart(LONG_TAIL, size="md", show_labels=True,
                                 variant="donut", center_text="100%")

                    ui.heading("Negative / zero values skipped silently",
                               level=3)
                    ui.text("Input contains 0 and -5 — both dropped.",
                            color="muted", size="xs")
                    ui.pie_chart(
                        [("A", 10), ("B", 0), ("C", -5), ("D", 30)],
                        size="sm",
                    )

                    ui.heading("Custom colour palette", level=3)
                    ui.pie_chart(
                        SAMPLE, size="sm",
                        colors=["error", "warning", "success", "info"],
                    )

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Pie sits comfortably in a KPI tile when "
                            "the legend is below.",
                            color="muted", size="sm")

                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Traffic share", color="muted",
                                        size="sm")
                                ui.pie_chart(SAMPLE, size="sm",
                                             variant="donut",
                                             center_text="12 944")
                        with ui.card():
                            with ui.vstack(gap="sm"):
                                ui.text("Quarterly mix", color="muted",
                                        size="sm")
                                ui.pie_chart(UNEVEN, size="sm",
                                             show_labels=True)

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
                    ui.pie_chart(data=[], empty_text='Nothing to show.',
                             empty_icon="unplug",
                             empty_description='No share to divide.')

                    ui.heading('Empty state — ``empty=`` takes over',
                               level=3)
                    ui.pie_chart(
                        data=[],
                        empty=lambda: ui.button('Import a set',
                                                icon_left="plus",
                                                variant="soft",
                                                size="sm"))

                    ui.heading("A11y", level=2)
                    ui.text(
                        "Charts emit ``role=\"img\"`` with an auto-"
                        "generated ``aria-label`` summarising the "
                        "slice count and kind (pie vs donut). "
                        "Override with ``attrs={\"aria-label\": "
                        "...}`` when the surrounding context already "
                        "describes the data.",
                        color="muted", size="sm",
                    )
                    ui.pie_chart(SAMPLE, size="sm",
                                 attrs={"aria-label":
                                        "Traffic share by channel"})

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop and every escape hatch is wired. "
                        "Set ``variant='donut'`` + populate "
                        "``center_text`` to render a KPI ring.",
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
