"""``NumberInput`` test bench — full 10-card gabarit.

Eight props : ``value`` / ``min`` / ``max`` / ``step`` / ``wheel`` /
``placeholder`` / ``disabled`` / ``required`` / ``color`` / ``size``.
Three events : ``change`` / ``focus`` / ``blur``. ``BINDABLE_PROPS =
("value", "disabled")`` — both get a dedicated Client playground card ;
min / max / step / wheel / placeholder / required / color / size stay
design-time.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/number_input"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── Playground state ──────────────────────────────────────────────────


class NumberInputPlayground(PageState):
    initial:     str  = field(default="42")
    min:         str  = field(default="")
    max:         str  = field(default="")
    step:        str  = field(default="1")
    placeholder: str  = field(default="Type a number…")
    wheel:       bool = field(default=True)
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class NumberInputEvents(PageState):
    log: list = field(default_factory=list)


class NumberInputServerEvents(ClientState, persist="memory"):
    value: float = field(default=0.0)


class NumberInputClient(ClientState, persist="memory"):
    """Mirror of NumberInput's BINDABLE_PROPS = ('value', 'disabled')."""

    amount:   float = field(default=42.0)
    disabled: bool  = field(default=False)


class NumberInputClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ──────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = NumberInputEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    log(f"change(value={value!r})")
def log_focus() -> None: log("focus")
def log_blur()  -> None: log("blur")


def clear_log() -> None:
    NumberInputEvents().log = []


def server_changed(state: NumberInputPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[NumberInputPlayground] re-renders server_panel automatically.
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


def parse_num(raw: str, default=None):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def build_preview(state: NumberInputPlayground) -> dict:
    # ⚠️ ``state.initial`` IS PASSED AS IS, with no ``parse_num``.
    #
    # A value read on a ``PageState`` carries a stamp (the original
    # field's name), and it is the ONLY thing attesting "the server is
    # authoritative". Any transformation — ``int()``, ``float()``,
    # ``parse_num()`` — returns a bare scalar and unwraps the stamp: the
    # component then believes itself client-owned, does not emit
    # ``value`` in ``_serverSync``, and its signal stays frozen at its
    # value from the first mount. The exact symptom: one changes the
    # control, the preview does not move until the page is reloaded.
    #
    # We can afford it although ``initial`` is a ``str`` (the bench wants
    # to be able to type emptiness and nonsense) because NumberInput
    # takes a stamped string in all three cases — checked:
    #   "42" → field 42.0   |   "" → null   |   "abc" → null
    # So ``parse_num`` protected against nothing the component does not
    # already do, and it cost the reactivity.
    #
    # ``step`` keeps its own: it is config, its re-sync depends on no
    # stamp (cf. the unconditional ``_serverSync`` on the component
    # side).
    kwargs: dict = {
        "value": state.initial,
        "step": parse_num(state.step, 1.0),
        "placeholder": state.placeholder,
        "wheel": state.wheel,
        "disabled": state.disabled,
        "required": state.required,
        "color": state.color,
        "size": state.size,
    }
    min_v = parse_num(state.min)
    max_v = parse_num(state.max)
    if min_v is not None:
        kwargs["min"] = min_v
    if max_v is not None:
        kwargs["max"] = max_v
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


@refreshable(deps=[NumberInputPlayground])
def server_panel() -> None:
    state = NumberInputPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("initial value"):
            ui.input(value=state.initial, on_change=server_changed)
        with control("min (empty = unbounded)"):
            ui.input(value=state.min, on_change=server_changed)
        with control("max (empty = unbounded)"):
            ui.input(value=state.max, on_change=server_changed)
        with control("step"):
            ui.input(value=state.step, on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("wheel (focused = scroll inc/dec)"):
            ui.switch(checked=state.wheel, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!w-32",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="age-input",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Age",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="--w: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=age",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Pick a number",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        ui.number_input(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(ui.number_input(**kwargs)),
    )


@refreshable(deps=[NumberInputEvents])
def events_panel() -> None:
    state = NumberInputEvents()

    ui.text(
        "NumberInput exposes three events : ``on_change`` (after "
        "settled value — typing then blur, click on stepper, or "
        "keyboard nudge), ``on_focus`` / ``on_blur``. One instance "
        "per event below — a single NumberInput carries only one "
        "server ``hx-post``.",
        color="muted", size="sm",
    )

    ses = NumberInputServerEvents()
    with ui.flex(wrap=True, gap="md", justify="center"):
        ui.number_input(value=ses.value, min=0, max=100,
                        on_change=log_change)
        ui.number_input(value=0, min=0, max=100, on_focus=log_focus)
        ui.number_input(value=0, min=0, max=100, on_blur=log_blur)

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
        ui.text("(no events yet — type, click steppers, or arrow keys)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.number_input(value=ses.value, min=0, max=100,
                                      on_change=log_change)
    emitted_html_block(
        "Emitted HTML (NumberInput with binding + on_change)",
        serialize_html(representative),
    )


# ──────────────────────────────────────────────────────────────────────
# Page
# ──────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("NumberInput", level=1)
            ui.text(
                "Numeric input with vertical ± stepper buttons. "
                "Native ``<input type=number>`` is blocked in "
                "``ui.input`` since this component shipped — use "
                "``ui.number_input`` for numeric values (proper "
                "clamp / step / float precision / stepper UI). "
                "Keyboard : ↑↓ ± step, PageUp/Down ± step×10. "
                "Wheel (focused) : scroll to inc/dec. Imperative : "
                "``.set / .clear / .focus / .blur / .increment / "
                ".decrement``.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Type, click steppers, tab + arrows, or "
                        "scroll while focused.",
                        color="muted", size="sm",
                    )

                    ui.heading("Basic", level=3)
                    ui.number_input(value=42)

                    ui.heading("With min / max", level=3)
                    ui.number_input(value=50, min=0, max=100)

                    ui.heading("Custom step (5)", level=3)
                    ui.number_input(value=0, step=5)

                    ui.heading(
                        "Float step (0.1) — drift handled", level=3,
                    )
                    ui.text(
                        "Click ▲ seven times from 0 → reads 0.7 "
                        "(not 0.7000000000000001).",
                        color="muted", size="xs",
                    )
                    ui.number_input(value=0, min=0, max=1, step=0.1)

                    ui.heading("Negative range", level=3)
                    ui.number_input(value=-25, min=-100, max=0, step=5)

                    ui.heading("Sizes (xs → xl)", level=3)
                    with ui.vstack(gap="md"):
                        for s in ui.each(SIZES):
                            with ui.vstack(gap="xs"):
                                ui.text(s, color="muted", size="xs")
                                ui.number_input(value=42, size=s)

                    ui.heading("Colors (focus ring)", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        for c in ui.each(COLORS):
                            with ui.vstack(gap="xs"):
                                ui.text(c, color="muted", size="xs")
                                ui.number_input(value=42, color=c)

                    ui.heading("Disabled / required", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.number_input(value=42, disabled=True)
                        ui.number_input(required=True,
                                        placeholder="required")

                    ui.heading("Wheel (scroll while focused)", level=3)
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.number_input(value=42, wheel=True)
                        ui.number_input(value=42, wheel=False)

                    ui.heading("name (form field key)", level=3)
                    ui.number_input(value=42, name="quantity")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("No bounds (unbounded)", level=3)
                    ui.number_input(value=1234567)

                    ui.heading(
                        "Value out of bounds (clamped on blur)",
                        level=3,
                    )
                    ui.number_input(value=50, min=0, max=100)

                    ui.heading(
                        "Bad input (NaN reverts on blur)", level=3,
                    )
                    ui.number_input(value=42, min=0, max=100)

                    ui.heading(
                        "Step doesn't divide range", level=3,
                    )
                    ui.number_input(value=0, min=0, max=10, step=3)

                    ui.heading("Float min / max / step", level=3)
                    ui.number_input(value=0.5, min=0.0, max=1.0,
                                    step=0.05)

                    ui.heading("Empty (null) value", level=3)
                    ui.number_input(placeholder="empty start")

                    ui.heading("Wheel disabled", level=3)
                    ui.number_input(value=42, wheel=False)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading("Inside a Form", level=3)
                    with ui.form():
                        with ui.vstack():
                            with ui.form_field(label="Name"):
                                ui.input(value="Jean")
                            ui.number_input(value=30, min=0, max=120,
                                            placeholder="Age")
                            with ui.hstack(justify="end"):
                                ui.button("Submit", type="submit",
                                          color="primary")

                    ui.heading("Quantity picker", level=3)
                    ui.number_input(value=1, min=1, max=99, step=1,
                                    color="success")

                    ui.heading("Price input (float)", level=3)
                    ui.number_input(value=19.99, min=0, step=0.01)

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Steppers : ``<button>`` with ``aria-label`` "
                        "and ``tabindex=\"-1\"`` so they don't steal "
                        "focus from the input. Input handles "
                        "keyboard ↑↓ / PageUp/Down / Home / End. "
                        "``inputmode=\"decimal\"`` for the numeric "
                        "keyboard on mobile, without the quirks of "
                        "native ``type=\"number\"``.",
                        color="muted", size="sm",
                    )
                    ui.number_input(value=42, min=0, max=100, step=5)

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
                        "Mirror of NumberInput's ``BINDABLE_PROPS = "
                        "('value', 'disabled')`` contract. Both flip "
                        "live via ``bz-attr:value`` (write-through) / "
                        "``bz-attr:disabled`` — no network round-trip. "
                        "min / max / step / wheel / color / size stay "
                        "design-time.",
                        color="muted", size="sm",
                    )
                    client = NumberInputClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value"):
                            ui.number_input(value=client.amount)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.number_input(value=client.amount,
                                         min=0, max=100,
                                         disabled=client.disabled)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — write-through binding on "
                        "value, bz-attr:disabled on disabled.",
                        serialize_html(
                            ui.number_input(value=client.amount,
                                             min=0, max=100,
                                             disabled=client.disabled)
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)

                    ui.heading("Mode 1 — Imperative only", level=3)
                    m1 = ui.number_input(value=10, min=0, max=100,
                                          step=5)
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set 0", on_click=m1.set(0))
                        ui.button("Set 50", on_click=m1.set(50))
                        ui.button("+5", on_click=m1.increment())
                        ui.button("-5", on_click=m1.decrement())
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())

                    ui.divider()

                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    bound = NumberInputClient(key="binding_only")
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.text("Value :", color="muted", size="sm")
                            ui.code(bound.amount, lang="text")
                        ui.number_input(value=bound.amount, min=0,
                                        max=100, color="warning")
                        with ui.hstack(wrap=True, gap="sm"):
                            ui.button("Force 0",
                                      on_click=bound.amount.set(0))
                            ui.button("Force 50",
                                      on_click=bound.amount.set(50))

                    ui.divider()

                    ui.heading("Mode 3 — Both (write-through)",
                               level=3)
                    both = NumberInputClient(key="both")
                    m3 = ui.number_input(value=both.amount, min=0,
                                          max=100, step=5)
                    with ui.hstack(wrap=True, gap="sm"):
                        ui.button("Set 25 via n.set()",
                                  on_click=m3.set(25))
                        ui.button("+5 via n.increment()",
                                  on_click=m3.increment())
                        ui.button("Focus", variant="ghost",
                                  on_click=m3.focus())

                    ui.divider()

                    preview = ui.number_input(value=bound.amount,
                                               min=0, max=100)
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
                        "pushing onto a ClientState list. Zero "
                        "network.",
                        color="muted", size="sm",
                    )
                    cevents = NumberInputClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.flex(justify="center"):
                        ui.number_input(
                            value=42,
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
                        '($bz.state.NumberInputClientEvents.default'
                        '.log || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — the native ``number`` input "
                        "fires change ; the client expression pushes "
                        "the new numeric value (as string).",
                        serialize_html(
                            ui.number_input(
                                value=42,
                                on_change=cevents.log.push(_new_value),
                            )
                        ),
                    )
