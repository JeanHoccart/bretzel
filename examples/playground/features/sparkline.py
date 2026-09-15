"""``Sparkline`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — sparkline data flows via
``@refreshable`` (the Server playground card demonstrates the
pattern with a tiny "shuffle data" button).
"""

from __future__ import annotations

import random

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field, form_value

from examples.playground.features.inspection import emitted_html_block


PATH = "/sparkline"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]

# Canonical sample series — short, monotonically interesting, no zero
# spikes (which can mask line artefacts).
SAMPLE = [4, 6, 5, 8, 7, 12, 10, 14, 13, 18, 16, 21]

# Pre-baked datasets the Server playground can pick from. Picking by
# label rather than typing JSON keeps the control simple.
DATA_PRESETS = {
    "rising":   [3, 5, 4, 7, 6, 9, 8, 11, 10, 13],
    "falling":  [13, 10, 11, 8, 9, 6, 7, 4, 5, 3],
    "noisy":    [5, 8, 3, 12, 6, 9, 4, 11, 7, 10],
    "flat":     [7, 7, 7, 7, 7, 7, 7, 7],
    "single":   [42],
    "negative": [-5, -3, -8, -2, -6, -1, -4],
    "mixed":    [-3, 1, -2, 4, -1, 5, 0, 3],
    "empty":    [],
}


class SparklinePlayground(PageState):
    color:         str  = field(default="primary")
    size:          str  = field(default="sm")
    width:         int  = field(default=160)
    smooth:        bool = field(default=False)
    area_fill:     bool = field(default=False)
    show_last_dot: bool = field(default=False)
    dataset:       str  = field(default="rising")
    # When non-empty, overrides ``dataset`` — populated by Shuffle.
    shuffled:      list = field(default_factory=list)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: SparklinePlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    # form_value("dataset") is the escape hatch to detect WHICH field changed:
    # picking a preset clears any prior shuffle so the toggle is honest.
    if form_value("dataset"):
        state.shuffled = []


def shuffle_data() -> None:
    state = SparklinePlayground()
    rng = random.Random()
    state.shuffled = [rng.randint(0, 20) for _ in range(rng.randint(8, 14))]


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: SparklinePlayground):
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
        "width": state.width,
        "smooth": state.smooth,
        "area_fill": state.area_fill,
        "show_last_dot": state.show_last_dot,
    }
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
    data = state.shuffled if state.shuffled else DATA_PRESETS.get(state.dataset, SAMPLE)
    return ui.sparkline(data, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SparklinePlayground])
def server_panel() -> None:
    state = SparklinePlayground()

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
            ui.number_input(value=state.width, min=40, max=480, step=20,
                            on_change=server_changed)
        with control("smooth"):
            ui.switch(checked=state.smooth, on_change=server_changed)
        with control("area_fill"):
            ui.switch(checked=state.area_fill, on_change=server_changed)
        with control("show_last_dot"):
            ui.switch(checked=state.show_last_dot, on_change=server_changed)
        with control("dataset"):
            ui.select(value=state.dataset,
                      options=[(k, k) for k in DATA_PRESETS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!opacity-60",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-spark",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Revenue trend",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.7",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=spark",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Last 12 weeks",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.hstack(justify="center", align="center", classes="min-h-16"):
        build_preview(state)

    with ui.hstack(justify="center"):
        ui.button("Shuffle data", variant="ghost", size="sm",
                  on_click=shuffle_data,
                  tooltip="Mutate the 'rising' preset and refresh — "
                          "shows server-driven data updates.")

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Sparkline", level=1)
            ui.text(
                "Inline single-series trend indicator. Drops next to "
                "a headline number on a KPI card or in a dense table "
                "row. No axes, no labels — the silhouette IS the "
                "summary. Live data updates flow through "
                "``@refreshable``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan across sizes, colors and "
                            "visual variants.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="center", gap="lg"):
                        for s in SIZES:
                            with ui.vstack(gap="xs", align="center"):
                                ui.sparkline(SAMPLE, size=s)
                                ui.text(s, color="muted", size="xs")

                    ui.heading("Colors", level=3)
                    with ui.hstack(align="center", gap="lg", wrap=True):
                        for c in COLORS:
                            with ui.vstack(gap="xs", align="center"):
                                ui.sparkline(SAMPLE, color=c)
                                ui.text(c, color="muted", size="xs")

                    ui.heading("Variants — smooth / area / dot", level=3)
                    with ui.hstack(align="center", gap="lg", wrap=True):
                        with ui.vstack(gap="xs", align="center"):
                            ui.sparkline(SAMPLE)
                            ui.text("default", color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.sparkline(SAMPLE, smooth=True)
                            ui.text("smooth", color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.sparkline(SAMPLE, area_fill=True)
                            ui.text("area_fill", color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.sparkline(SAMPLE, show_last_dot=True)
                            ui.text("last dot", color="muted", size="xs")
                        with ui.vstack(gap="xs", align="center"):
                            ui.sparkline(SAMPLE, smooth=True,
                                         area_fill=True, show_last_dot=True)
                            ui.text("all on", color="muted", size="xs")

                    ui.heading("Width", level=3)
                    ui.text("``width=`` clamps the SVG horizontally. "
                            "Height comes from ``size=``.",
                            color="muted", size="xs")
                    with ui.vstack(gap="sm", align="start"):
                        for w in (80, 160, 240, 360):
                            with ui.hstack(align="center", gap="md"):
                                ui.sparkline(SAMPLE, width=w)
                                ui.text(f"width={w}", color="muted",
                                        size="xs")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that often surface rendering bugs.",
                            color="muted", size="sm")

                    ui.heading("Empty data", level=3)
                    ui.text("Renders the SVG frame but no path. "
                            "Aria summary reports the empty state.",
                            color="muted", size="xs")
                    with ui.hstack(align="center"):
                        ui.sparkline([])

                    ui.heading("Single point", level=3)
                    ui.text("One value — degenerate x domain, falls "
                            "back to a centred dot/line.",
                            color="muted", size="xs")
                    with ui.hstack(align="center"):
                        ui.sparkline([42], show_last_dot=True)

                    ui.heading("Constant series (zero variance)", level=3)
                    ui.text("Degenerate y domain. Linear scale "
                            "collapses to the midpoint → flat line.",
                            color="muted", size="xs")
                    with ui.hstack(align="center"):
                        ui.sparkline([7, 7, 7, 7, 7, 7])

                    ui.heading("Negative-only values", level=3)
                    with ui.hstack(align="center"):
                        ui.sparkline([-5, -3, -8, -2, -6, -1, -4])

                    ui.heading("Mixed positive / negative", level=3)
                    with ui.hstack(align="center"):
                        ui.sparkline([-3, 1, -2, 4, -1, 5, 0, 3],
                                     area_fill=True)

                    ui.heading("Tuple data shape", level=3)
                    ui.text("``[(x, y), …]`` is accepted alongside the "
                            "list-of-numbers shortcut.",
                            color="muted", size="xs")
                    with ui.hstack(align="center"):
                        ui.sparkline([(0, 5), (1, 12), (2, 7),
                                      (3, 15), (4, 9), (5, 18)])

                    ui.heading("Very dense series (60 points)", level=3)
                    ui.text("Stays smooth at typical KPI widths — SVG "
                            "handles ~1000 nodes before performance "
                            "degrades.",
                            color="muted", size="xs")
                    dense = [
                        ((i * 7) % 23) + ((i * 3) % 11) for i in range(60)
                    ]
                    with ui.hstack(align="center"):
                        ui.sparkline(dense, width=320, size="md",
                                     smooth=True)

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("The two canonical homes : next to a KPI "
                            "number, inside a table row.",
                            color="muted", size="sm")

                    ui.heading("KPI card", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "md": 3},
                                 gap="md"):
                        for label, value, dataset, color in (
                            ("Revenue", "$48 312", "rising", "success"),
                            ("Active users", "12 944", "noisy", "primary"),
                            ("Error rate", "0.42 %", "falling", "warning"),
                        ):
                            with ui.card():
                                with ui.vstack(gap="xs"):
                                    ui.text(label, color="muted",
                                            size="sm")
                                    with ui.hstack(align="end",
                                                   justify="between"):
                                        ui.heading(value, level=3,
                                                   size="2xl")
                                        ui.sparkline(
                                            DATA_PRESETS[dataset],
                                            color=color, size="md",
                                            width=100, smooth=True,
                                            area_fill=True,
                                        )

                    ui.heading("Inside a table row", level=3)
                    rows = [
                        {"name": "Acme Corp",   "trend": "rising",
                         "score": 87},
                        {"name": "Globex Inc",  "trend": "noisy",
                         "score": 64},
                        {"name": "Initech Ltd", "trend": "falling",
                         "score": 31},
                    ]
                    ui.table(
                        columns=[
                            ui.column("name", label="Account"),
                            ui.column(
                                "trend", label="7-day",
                                render=lambda v, _row: ui.sparkline(
                                    DATA_PRESETS[v], size="xs",
                                    width=80,
                                    color=(
                                        "success" if v == "rising"
                                        else "warning" if v == "noisy"
                                        else "error"
                                    ),
                                ),
                            ),
                            ui.column("score", label="Score",
                                      align="right"),
                        ],
                        rows=rows,
                        size="sm",
                    )

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Sparkline emits ``role=\"img\"`` and a "
                        "default ``aria-label`` summarising the "
                        "trend (``\"Sparkline — N points, min X, "
                        "max Y\"``). Override via the Server "
                        "playground when the context already "
                        "describes the data.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="lg"):
                        ui.sparkline(SAMPLE,
                                     attrs={"aria-label":
                                            "Revenue, last 12 weeks"})
                        ui.sparkline([],
                                     attrs={"aria-label":
                                            "No data this week"})

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control. The ``Shuffle data`` button "
                        "mutates the 'rising' preset server-side and "
                        "refreshes — the entire SVG re-renders and "
                        "idiomorph swaps the new path attributes.",
                        color="muted", size="sm",
                    )
                    server_panel()
