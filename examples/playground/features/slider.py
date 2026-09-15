"""``Slider`` test bench — full 10-card gabarit (full 7-section
gabarit, S2 split into 4 visual cards). ``BINDABLE_PROPS = ("value",
"disabled")`` — both get a dedicated Client playground card ; min /
max / step / range / required / color / size stay design-time.

Eight props : ``value`` / ``min`` / ``max`` / ``step`` / ``range``
/ ``disabled`` / ``required`` / ``color`` / ``size``. Three events :
``change`` / ``focus`` / ``blur``. Tooltip with the live value is
built-in (visible on hover / focus / drag — no prop to configure in
v1, lean scope).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/slider"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── Playground state ──────────────────────────────────────────────────


class SliderPlayground(PageState):
    range:    bool  = field(default=False)
    min:      float = field(default=0.0)
    max:      float = field(default=100.0)
    step:     float = field(default=1.0)
    disabled: bool  = field(default=False)
    required: bool  = field(default=False)
    color:    str   = field(default="primary")
    size:     str   = field(default="md")
    initial:  str   = field(default="50")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class SliderEvents(PageState):
    log: list = field(default_factory=list)


class SliderServerEvents(ClientState, persist="memory"):
    value: float = field(default=50.0)


class SliderClient(ClientState, persist="memory"):
    """Mirror of Slider's BINDABLE_PROPS = ('value', 'disabled')."""

    volume:   float = field(default=50.0)
    disabled: bool  = field(default=False)


class SliderRangeClient(ClientState, persist="memory"):
    span: list = field(default_factory=lambda: [20.0, 80.0])


class SliderClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ──────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = SliderEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None: log(f"change(value={value!r})")
def log_focus()  -> None: log("focus")
def log_blur()   -> None: log("blur")


def clear_log() -> None:
    SliderEvents().log = []


def server_changed(state: SliderPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


# ── Helpers ───────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def parse_initial(raw: str, is_range: bool):
    """Parse the initial value string. Range expects 'a,b' ;
    single expects a number."""
    try:
        if is_range:
            parts = [float(p.strip()) for p in raw.split(",") if p.strip()]
            return parts if len(parts) == 2 else [0.0, 100.0]
        return float(raw)
    except (ValueError, TypeError):
        return [0.0, 100.0] if is_range else 0.0


def build_preview(state: SliderPlayground) -> dict:
    kwargs: dict = {
        "min": state.min,
        "max": state.max,
        "step": state.step,
        "range": state.range,
        "disabled": state.disabled,
        "required": state.required,
        "color": state.color,
        "size": state.size,
        "value": parse_initial(state.initial, state.range),
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# ──────────────────────────────────────────────────────────────────────
# Refreshable panels
# ──────────────────────────────────────────────────────────────────────


@refreshable(deps=[SliderPlayground])
def server_panel() -> None:
    state = SliderPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("range"):
            ui.switch(checked=state.range, on_change=server_changed)
        with control("min"):
            ui.input(value=state.min, on_change=server_changed)
        with control("max"):
            ui.input(value=state.max, on_change=server_changed)
        with control("step"):
            ui.input(value=state.step, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled,
                      on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required,
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control(
            "initial (single: '50' / range: '20,80')"
        ):
            ui.input(value=state.initial, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!w-72",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-slider",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Volume",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="--track-width: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=slider",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Drag to set",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        ui.slider(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(ui.slider(**kwargs)),
    )


@refreshable(deps=[SliderEvents])
def events_panel() -> None:
    state = SliderEvents()

    ui.text(
        "Slider exposes three events : ``on_change`` (after every "
        "settled value change — keyboard nudge or pointer up), "
        "``on_focus`` / ``on_blur`` on the handle. The handler "
        "receives the new ``value=`` via FormData (autoname). One "
        "instance per event below — a single Slider carries only "
        "one server ``hx-post``.",
        color="muted", size="sm",
    )

    ses = SliderServerEvents()
    with ui.flex(wrap=True, gap="lg", justify="center"):
        ui.slider(value=ses.value, on_change=log_change)
        ui.slider(value=50, on_focus=log_focus)
        ui.slider(value=50, on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 12)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-12:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet — drag or tab onto the slider)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.slider(value=ses.value, on_change=log_change)
    emitted_html_block(
        "Emitted HTML (Slider with value-binding + on_change)",
        serialize_html(representative),
    )


# ──────────────────────────────────────────────────────────────────────
# Page
# ──────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Slider", level=1)
            ui.text(
                "Drag-to-pick numeric input. Single (one handle, "
                "scalar value) or range (``range=True``, two "
                "handles + ``[start, end]`` array). Tooltip with "
                "the live value pops up on hover / focus / drag — "
                "built-in, no config in v1. Keyboard : arrows / "
                "PageUp/Down / Home / End. Imperative API : "
                "``.set / .clear / .focus / .blur``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Drag the handles, hover for the tooltip, "
                        "or tab + arrow keys for keyboard.",
                        color="muted", size="sm",
                    )

                    ui.heading("Single", level=3)
                    ui.slider(value=30)

                    ui.heading("Range", level=3)
                    ui.slider(value=[20, 80], range=True)

                    ui.heading("Custom min / max / step", level=3)
                    ui.slider(value=50, min=0, max=200, step=10)

                    ui.heading("Sizes (xs → xl)", level=3)
                    with ui.vstack(gap="md"):
                        for s in ui.each(SIZES):
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                ui.slider(value=50, size=s)

                    ui.heading("Colors", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in ui.each(COLORS):
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.slider(value=60, color=c)

                    ui.heading("Disabled / required", level=3)
                    ui.slider(value=40, disabled=True)
                    ui.slider(value=40, required=True)

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Min = max (no-op)", level=3)
                    ui.slider(value=5, min=5, max=5)

                    ui.heading("Step > range", level=3)
                    ui.slider(value=0, min=0, max=10, step=50)

                    ui.heading("Negative range", level=3)
                    ui.slider(value=-25, min=-100, max=0, step=5)

                    ui.heading("Float step", level=3)
                    ui.slider(value=0.5, min=0, max=1, step=0.1)

                    ui.heading(
                        "Range with collapsed values [50, 50]",
                        level=3,
                    )
                    ui.slider(value=[50, 50], range=True)

                    ui.heading(
                        "Range with reversed initial [80, 20] "
                        "(auto-sorted)", level=3,
                    )
                    ui.slider(value=[80, 20], range=True)

                    ui.heading(
                        "Value out of bounds (clamped on first drag)",
                        level=3,
                    )
                    ui.slider(value=150, min=0, max=100)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading("Inside a form", level=3)
                    with ui.form():
                        with ui.vstack():
                            with ui.form_field(label="Name"):
                                ui.input(value="Jean")
                            ui.slider(value=50, min=0, max=100)
                            with ui.hstack(justify="end"):
                                ui.button("Submit", type="submit",
                                          color="primary")

                    ui.heading("Inside a Card with label", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.text("Volume", color="muted", size="sm")
                            ui.slider(value=75, color="success")

                    ui.heading(
                        "Range : price filter", level=3,
                    )
                    ui.slider(value=[100, 500], min=0, max=1000,
                              step=50, range=True, color="info")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Each handle wears ``role=\"slider\"`` + "
                        "``aria-valuemin`` / ``aria-valuemax`` / "
                        "reactive ``:aria-valuenow``. Handles are "
                        "focusable (``tabindex=\"0\"``). Range "
                        "handles get ``aria-label=\"Range start\"`` / "
                        "``\"Range end\"`` so screen readers can "
                        "distinguish them.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Keyboard : Arrow keys ± step, "
                        "PageUp/Down ± step×10, Home / End to bounds.",
                        color="muted", size="sm",
                    )
                    ui.slider(value=42)

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Slider's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Dragging "
                        "the control below writes straight through "
                        "the binding — no network round-trip ; min / "
                        "max / step / range / required / color / "
                        "size stay design-time.",
                        color="muted", size="sm",
                    )
                    client = SliderClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            ui.slider(value=client.volume, min=0, max=100)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.slider(value=client.volume, min=0, max=100,
                                  disabled=client.disabled)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — the bz-data scope's _read/"
                        "_write route through the bound value path ; "
                        "disabled drives _disabledState() via "
                        "bz-class on the track/root, no static attr.",
                        serialize_html(
                            ui.slider(value=client.volume, min=0, max=100,
                                      disabled=client.disabled)
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario played three ways.",
                        color="muted", size="sm",
                    )

                    ui.heading("Mode 1 — Imperative only", level=3)
                    m1 = ui.slider(value=30)
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set 10", on_click=m1.set(10))
                        ui.button("Set 90", on_click=m1.set(90))
                        ui.button("Reset", variant="outline",
                                  on_click=m1.clear())

                    ui.divider()

                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    bound = SliderClient(key="binding_only")
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.text("Value :", color="muted", size="sm")
                            ui.code(bound.volume, lang="text")
                        ui.slider(value=bound.volume, color="warning")
                        with ui.hstack(wrap=True, gap="sm"):
                            ui.button("Force 0",
                                      on_click=bound.volume.set(0))
                            ui.button("Force 50",
                                      on_click=bound.volume.set(50))
                            ui.button("Force 100",
                                      on_click=bound.volume.set(100))

                    ui.divider()

                    ui.heading("Mode 3 — Both (write-through)",
                               level=3)
                    both = SliderClient(key="both")
                    m3 = ui.slider(value=both.volume)
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set 25 via slider.set()",
                                  on_click=m3.set(25))
                        ui.button("Set 75 via binding.set()",
                                  on_click=both.volume.set(75))
                        ui.button("Focus", variant="ghost",
                                  on_click=m3.focus())

                    ui.divider()

                    ui.heading(
                        "Bonus — range with array binding", level=3,
                    )
                    rng = SliderRangeClient(key="rng")
                    rng_slider = ui.slider(value=rng.span,
                                            min=0, max=100,
                                            range=True,
                                            color="success")
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Span 0-100",
                                  on_click=rng.span.set([0, 100]))
                        ui.button("Span 40-60",
                                  on_click=rng.span.set([40, 60]))
                        ui.button("Reset (full)", variant="outline",
                                  on_click=rng_slider.clear())

                    ui.divider()

                    preview = ui.slider(value=bound.volume)
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only)",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "All three events wired to client expressions "
                        "that push onto a ClientState list. Zero "
                        "network.",
                        color="muted", size="sm",
                    )
                    cevents = SliderClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.flex(justify="center"):
                        ui.slider(
                            value=50,
                            on_change=cevents.log.push(_new_value),
                            on_focus=cevents.log.push("focus"),
                            on_blur=cevents.log.push("blur"),
                        )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text(
                            "Live log (client-reactive — no refresh)",
                            color="muted", size="sm",
                        )
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.SliderClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — the native ``range`` input "
                        "fires change ; the client expression pushes "
                        "``$event.target.value`` (the slider's new "
                        "numeric value as string).",
                        serialize_html(
                            ui.slider(
                                value=50,
                                on_change=cevents.log.push(_new_value),
                            )
                        ),
                    )
