"""``Histogram`` test bench.

Seven cards: Reference / Edge cases / Composability / A11y / Server
playground / Server events / Client events. A histogram is a bar chart
over tranches it counts itself: the cards try the tranches (a step of 1,
a wider step, irregular bins, a bonus past the scale), the mean, and the
click, which says the tranche — ``on_item_click(low, high)``.
"""

from __future__ import annotations

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block

PATH = "/histogram"

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info", "muted"]

MARKS = [12.5, 14, 8, 16.5, 11, 9.5, 15, 13, 18, 7, 12, 14.5, 10, 16, 13.5,
         11.5, 19, 6.5, 12, 15.5, 20, 9, 13, 17]
BINS = {
    "none": None,
    "quarters": [0, 5, 10, 15, 20],
    "bands": [0, 9, 13, 15, 20],
}


class HistogramClientEvents(ClientState, persist="memory"):
    """The Client events card's log — on the browser side."""

    log: list = field(default_factory=list)


class HistogramEvents(PageState):
    log: list = field(default_factory=list)


def log_click(low, high) -> None:
    state = HistogramEvents()
    state.log = [f"click → [{low}, {high}[", *state.log][:10]


def clear_log() -> None:
    HistogramEvents().log = []


class HistogramPlayground(PageState):
    color:          str  = field(default="primary")
    size:           str  = field(default="md")
    width:          int  = field(default=600)
    x_min:          str  = field(default="0")
    x_max:          str  = field(default="20")
    step:           str  = field(default="")
    bins:           str  = field(default="none")
    show_mean:      bool = field(default=True)
    show_values:    bool = field(default=False)
    show_axis:      bool = field(default=True)
    show_gridlines: bool = field(default=True)
    show_data:      bool = field(default=False)
    y_max:          str  = field(default="")
    x_label:        str  = field(default="Mark")
    y_label:        str  = field(default="Pupils")
    dataset:        str  = field(default="marks")
    empty_text:     str  = field(default="")
    empty_icon:     str  = field(default="bar-chart-3")
    empty_desc:     str  = field(default="")
    empty_escape:   bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: HistogramPlayground) -> None:
    """The typed parameter receives the changed control's value."""


def number(typed: str) -> float | None:
    """A number typed in its field, or none."""
    try:
        return float(typed)
    except ValueError:
        return None


def dataset(state: HistogramPlayground) -> list[float]:
    return {
        "marks": MARKS,
        "bonus": [*MARKS, 21],
        "empty": [],
    }.get(state.dataset, MARKS)


def build_preview(state: HistogramPlayground):
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
        "width": state.width,
        "show_mean": state.show_mean,
        "show_values": state.show_values,
        "show_axis": state.show_axis,
        "show_gridlines": state.show_gridlines,
        "show_data": state.show_data,
    }
    bins = BINS.get(state.bins)
    if bins:
        kwargs["bins"] = bins
    else:
        if number(state.x_min) is not None:
            kwargs["x_min"] = number(state.x_min)
        if number(state.x_max) is not None:
            kwargs["x_max"] = number(state.x_max)
        if number(state.step) is not None:
            kwargs["step"] = number(state.step)
    if number(state.y_max) is not None:
        kwargs["y_max"] = number(state.y_max)
    if state.x_label:
        kwargs["x_label"] = state.x_label
    if state.y_label:
        kwargs["y_label"] = state.y_label
    if state.empty_text:
        kwargs["empty_text"] = state.empty_text
    if state.empty_icon:
        kwargs["empty_icon"] = state.empty_icon
    if state.empty_desc:
        kwargs["empty_description"] = state.empty_desc
    if state.empty_escape:
        kwargs["empty"] = lambda: ui.button("Type the first marks", variant="soft", size="sm")
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    if state.aria_label:
        kwargs["attrs"] = {"aria-label": state.aria_label}
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    data = dataset(state)
    if bins and any(not bins[0] <= v <= bins[-1] for v in data):
        data = [v for v in data if bins[0] <= v <= bins[-1]]
    return ui.histogram(data, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = HistogramPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("dataset"):
            ui.select(value=state.dataset, on_change=server_changed,
                      options=[("marks", "24 marks out of 20"),
                               ("bonus", "… and a 21 (bonus)"),
                               ("empty", "empty")])
        with control("x_min (empty = from the data)"):
            ui.input(value=state.x_min, placeholder="0", on_change=server_changed)
        with control("x_max (empty = from the data)"):
            ui.input(value=state.x_max, placeholder="20", on_change=server_changed)
        with control("step (empty = 1 up to 40 wide)"):
            ui.input(value=state.step, placeholder="5", on_change=server_changed)
        with control("bins (instead of the three above)"):
            ui.select(value=state.bins, on_change=server_changed,
                      options=[("none", "none"), ("quarters", "[0, 5, 10, 15, 20]"),
                               ("bands", "[0, 9, 13, 15, 20]")])
        with control("show_mean"):
            ui.switch(checked=state.show_mean, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
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
        with control("show_data"):
            ui.switch(checked=state.show_data, on_change=server_changed)
        with control("y_max (empty = none)"):
            ui.input(value=state.y_max, placeholder="10", on_change=server_changed)
        with control("x_label"):
            ui.input(value=state.x_label, placeholder="Mark", on_change=server_changed)
        with control("y_label"):
            ui.input(value=state.y_label, placeholder="Pupils", on_change=server_changed)
        with control("empty_text (dataset='empty')"):
            ui.input(value=state.empty_text, placeholder="No mark yet",
                     on_change=server_changed)
        with control("empty_icon (dataset='empty')"):
            ui.input(value=state.empty_icon, placeholder="bar-chart-3",
                     on_change=server_changed)
        with control("empty_description (dataset='empty')"):
            ui.input(value=state.empty_desc, placeholder="Marks arrive with the first copy.",
                     on_change=server_changed)
        with control("empty= (escape hatch, dataset='empty')"):
            ui.switch(checked=state.empty_escape, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="border rounded-xl p-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-histogram",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Marks of the test",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="The spread",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible, on_change=server_changed,
                      options=[("on", "True (default)"), ("off", "False (skip render)")])
    ui.divider()
    with ui.flex(justify="center"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable
def events_panel() -> None:
    state = HistogramEvents()
    with ui.vstack():
        ui.text("Click a tranche — or Tab to the chart, the arrows, Enter. The "
                "handler receives its bounds: on_item_click(low, high).",
                color="muted", size="sm")
        with ui.flex(justify="center"):
            ui.histogram(MARKS, x_min=0, x_max=20, step=5, on_item_click=log_click,
                         show_values=True, width=480)
        ui.divider()
        with ui.hstack(justify="between", align="center"):
            ui.text("Server log (latest 10)", color="muted", size="xs")
            ui.button("Clear", variant="ghost", size="xs", on_click=clear_log)
        if not state.log:
            ui.text("No clicks yet.", color="muted", size="sm")
        for entry in state.log:
            ui.text(entry, size="sm")
        ui.divider()
        emitted_html_block(
            "Emitted HTML (representative — two tranches)",
            serialize_html(ui.histogram([3, 7], x_min=0, x_max=10, step=5,
                                        on_item_click=log_click)),
        )


def client_events_panel() -> None:
    """The SAME event on a client expression: the log is a ClientState,
    no request leaves."""
    events = HistogramClientEvents()
    ui.text("``on_item_click`` wired to a client expression that pushes onto "
            "a ClientState. Zero requests.", color="muted", size="sm")
    clicked = ClientExpression("new Date().toLocaleTimeString() + ' — ' + '[' + $event.detail.low + ', ' + $event.detail.high + '['")
    ui.histogram(MARKS, x_min=0, x_max=20, step=5,
                 on_item_click=events.log.push(clicked), width=480)
    ui.divider()
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (client-side — no refresh)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=events.log.clear())
    log_text = ClientExpression(
        "($bz.state.HistogramClientEvents.default.log || []).join('\\n') ||"
        " '(no events yet — click the demo above)'"
    )
    ui.text(log_text, color="muted", size="sm", classes="font-mono whitespace-pre")
    ui.divider()
    emitted_html_block(
        "Emitted HTML (click client)",
        serialize_html(ui.histogram([3, 7], x_min=0, x_max=10, step=5,
                                    on_item_click=events.log.push(clicked))),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Histogram", level=1)
        ui.text("Raw values counted per tranche, drawn as bars: a step of 1 "
                "counts per point, a wider step or irregular bins group them, "
                "show_mean marks the mean.", color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("A step of 1 — per point", size="xs", color="muted")
                    ui.histogram(MARKS, x_min=0, x_max=20, show_mean=True, size="sm")
                with ui.vstack(gap="xs"):
                    ui.text("step=5 — the top in the last tranche", size="xs",
                            color="muted")
                    ui.histogram(MARKS, x_min=0, x_max=20, step=5, show_values=True,
                                 size="sm", color="info")
                with ui.vstack(gap="xs"):
                    ui.text("bins=[0, 9, 13, 15, 20]", size="xs", color="muted")
                    ui.histogram(MARKS, bins=[0, 9, 13, 15, 20], show_values=True,
                                 size="sm", color="success")

            # The two rows every component page shows, under their h3: the
            # visual audit anchors on them (``tests/audit``).
            ui.heading("Sizes", level=3)
            with ui.vstack(gap="md"):
                for size in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(size, color="muted", size="xs")
                        ui.histogram(MARKS, x_min=0, x_max=20, step=5, size=size,
                                     width=480)

            ui.heading("Colors", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                for color in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(color, color="muted", size="xs")
                        ui.histogram(MARKS, x_min=0, x_max=20, step=5, color=color,
                                     width=400, size="sm")

        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("A 21/20 with a bonus: x_max is a minimum", size="xs",
                            color="muted")
                    ui.histogram([*MARKS, 21], x_min=0, x_max=20, size="sm")
                with ui.vstack(gap="xs"):
                    ui.text("No x_min: from the lowest value", size="xs", color="muted")
                    ui.histogram(MARKS, size="sm")
                with ui.vstack(gap="xs"):
                    ui.text("A test out of 60: about ten tranches", size="xs",
                            color="muted")
                    ui.histogram([m * 3 for m in MARKS], x_min=0, x_max=60, size="sm")
                with ui.vstack(gap="xs"):
                    ui.text("Empty", size="xs", color="muted")
                    ui.histogram([], empty_text="No mark yet",
                                 empty_description="Marks arrive with the first copy.")

        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            with ui.card(), ui.vstack(gap="sm"):
                ui.text("DS · Les mélanges", color="muted", size="sm")
                ui.heading("12,6 / 20", level=3, size="2xl")
                ui.histogram(MARKS, x_min=0, x_max=20, step=5, size="sm",
                             show_axis=False, show_gridlines=False, width=320)

        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text("Like every chart: role=\"img\" and an aria-label (« Histogram — "
                    "4 categories »), the table behind the drawing for a screen "
                    "reader, and one tab stop — the arrows walk the tranches.",
                    color="muted", size="sm")
            ui.histogram(MARKS, x_min=0, x_max=20, step=5, size="sm", width=480,
                         attrs={"aria-label": "Marks of the test, by quarter of the scale"})

        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text("Every prop wired to a control; the Emitted HTML follows.",
                    color="muted", size="sm")
            server_panel()

        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            client_events_panel()
