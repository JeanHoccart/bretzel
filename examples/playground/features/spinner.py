"""``Spinner`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` so no Client cards — the
spinner is a purely visual loading indicator with nothing to mutate
mid-flight. Toggle visibility from the parent via the universal
``visible=`` modifier instead.

Two props (``size`` / ``color``), no events, no slots.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/spinner"


SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted", "current"]


class SpinnerPlayground(PageState):
    size:        str = field(default="md")
    color:       str = field(default="primary")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: SpinnerPlayground) -> None:
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


def build_preview(state: SpinnerPlayground):
    kwargs: dict = {
        "size": state.size,
        "color": state.color,
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
    return ui.spinner(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SpinnerPlayground])
def server_panel() -> None:
    state = SpinnerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!opacity-60",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-spinner",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Loading data",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.5",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=spinner",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Loading…",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center", classes="min-h-16"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Spinner", level=1)
            ui.text(
                "Pure-CSS loading indicator — one opinionated look "
                "(a rotating ring), no SVG, no JS. The Server "
                "playground card stress-tests every prop ; the "
                "emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="center"):
                        for s in SIZES:
                            ui.spinner(size=s)

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True, align="center"):
                        for c in COLORS[:-1]:  # drop 'current' — needs ctx
                            ui.spinner(color=c)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("``color=\"current\"`` inherits parent color",
                               level=3)
                    ui.text(
                        "Useful when nested inside coloured surfaces "
                        "(a Button's loading spinner inherits the "
                        "button's text colour this way).",
                        color="muted", size="xs",
                    )
                    with ui.hstack(align="center"):
                        with ui.flex(classes="text-error"):
                            ui.spinner(color="current")
                        with ui.flex(classes="text-success"):
                            ui.spinner(color="current")
                        with ui.flex(classes="text-primary"):
                            ui.spinner(color="current")

                    ui.heading("Very large via classes=", level=3)
                    with ui.hstack(align="center"):
                        ui.spinner(size="xl", classes="!h-24 !w-24")

                    ui.heading("Smallest readable (xs)", level=3)
                    with ui.hstack(align="center"):
                        ui.spinner(size="xs")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Spinner is most often used inside other "
                            "components — Button's loading mutex bakes "
                            "it in automatically.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.button (loading mutex)", level=3)
                    with ui.hstack():
                        ui.button("Saving",     loading=True)
                        ui.button("Submitting", loading=True,
                                  variant="outline")
                        ui.button("Working",    loading=True,
                                  variant="ghost", color="error")

                    ui.heading("Inside ui.card (load placeholder)", level=3)
                    with ui.hstack():
                        with ui.card():
                            with ui.vstack(gap="sm", align="center"):
                                ui.spinner(size="lg")
                                ui.text("Loading data…",
                                        color="muted", size="sm")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.hstack():
                        with ui.tooltip("Background sync in progress"):
                            ui.spinner(color="info")

                    ui.heading("Next to text (hstack)", level=3)
                    with ui.hstack(align="center"):
                        ui.spinner(size="sm", color="muted")
                        ui.text("Refreshing items…", color="muted")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Spinner emits ``role=\"status\"`` and a default "
                        "``aria-label=\"Loading\"`` so screen readers "
                        "announce the loading state. Override the label "
                        "via the ``aria-label`` control in the Server "
                        "playground below.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center"):
                        ui.spinner(aria_label="Uploading photo")
                        ui.spinner(size="lg", aria_label="Compressing file")
                        ui.spinner(color="info",
                                   aria_label="Fetching dashboard")

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "The real test bench. Every prop AND every "
                        "escape hatch is wired to a control ; the "
                        "preview and the emitted HTML both refresh on "
                        "every change.",
                        color="muted", size="sm",
                    )
                    server_panel()
