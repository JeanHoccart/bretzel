"""``Switch`` test bench.

Ten visual cards : full gabarit. ``BINDABLE_PROPS = ("checked",
"disabled")`` — value + lock are bindable ; visual axes
(size / color) stay design-time.

Seven props : ``checked`` / ``name`` (autoname from ``checked``) /
``value`` / ``label`` / ``disabled`` / ``color`` / ``size``. Three
events : ``change`` / ``focus`` / ``blur``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/switch"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class SwitchPlayground(PageState):
    checked:     bool = field(default=False)
    label:       str  = field(default="Notifications enabled")
    value:       str  = field(default="")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class SwitchEvents(PageState):
    log: list = field(default_factory=list)


class SwitchClient(ClientState, persist="memory"):
    """Mirror of Switch's BINDABLE_PROPS = ('checked', 'disabled')."""

    checked:  bool = field(default=False)
    disabled: bool = field(default=False)


class SwitchClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = SwitchEvents()
    state.log = [*state.log, name]


def log_change()  -> None: log("change")
def log_focus()   -> None: log("focus")
def log_blur()    -> None: log("blur")


def clear_log() -> None:
    state = SwitchEvents()
    state.log = []


def server_changed(state: SwitchPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(checked: bool = False) -> None:
    log(f"playground-server-change(checked={checked})")


_CLIENT_CHANGE_EXPR = "$el.parentElement.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: SwitchPlayground):
    kwargs: dict = {
        "checked": state.checked,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
    }
    if state.label:
        kwargs["label"] = state.label
    if state.value:
        kwargs["value"] = state.value
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
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return ui.switch(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SwitchPlayground])
def server_panel() -> None:
    state = SwitchPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("checked"):
            ui.switch(checked=state.checked, on_change=server_changed)
        with control("label"):
            ui.input(value=state.label,
                     placeholder="Notifications enabled",
                     on_change=server_changed)
        with control("value (form submission)"):
            ui.input(value=state.value, placeholder="on",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-switch",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Toggle notifications",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="margin-top: 4px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=switch",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Toggle in-app notifications",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[SwitchEvents])
def events_panel() -> None:
    state = SwitchEvents()

    with ui.hstack(wrap=True, gap="lg", justify="center"):
        ui.switch(label="change",
                  on_change=log_change)
        ui.switch(label="focus",
                  on_focus=log_focus)
        ui.switch(label="blur",
                  on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — toggle one of the switches "
                "above to fire its event)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the 'change' switch)",
        serialize_html(
            ui.switch(label="change", on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Switch", level=1)
            ui.text(
                "Boolean toggle rendered as a sliding rail. Same DOM "
                "idiom as Checkbox (real ``<input type=\"checkbox\">`` "
                "hidden sr-only, two visual fakes for the track + "
                "thumb), just a different visual identity. Three ways "
                "to drive the ``checked`` state : built-in label "
                "click (simplest), capture the instance + call "
                "``.toggle()`` / "
                "``.set(bool)`` (imperative API — default for purely-"
                "visual switches), or ``checked=ClientBinding`` (when "
                "another component needs to read or react to the "
                "state). The 3 modes are compared side-by-side in "
                "Card 9. The Server playground card stress-tests "
                "every prop ; the emitted HTML is shown live "
                "underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.vstack():
                        for s in SIZES:
                            ui.switch(label=s, size=s, checked=True)

                    ui.heading("Colors (when checked)", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.switch(label=c.title(),
                                      color=c, checked=True)

                    ui.heading("State", level=3)
                    with ui.vstack():
                        ui.switch(label="Off")
                        ui.switch(label="On", checked=True)
                        ui.switch(label="Disabled", disabled=True)
                        ui.switch(label="Disabled + on",
                                  disabled=True, checked=True)

                    ui.heading("Without label", level=3)
                    with ui.hstack(gap="lg"):
                        ui.switch()
                        ui.switch(checked=True)
                        ui.switch(disabled=True)

                    ui.heading(
                        "Basic — external triggers via "
                        ".toggle() / .set(bool)",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance and call ``.toggle()`` / "
                        "``.set(bool)`` — client-local state, no "
                        "ClientState declared. The imperative API is "
                        "the default style for purely-visual "
                        "switches.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md", wrap=True):
                        s = ui.switch(label="Toggle me externally")
                        ui.button("Check",
                                  size="sm",
                                  on_click=s.set(True))
                        ui.button("Uncheck",
                                  variant="ghost", size="sm",
                                  on_click=s.set(False))
                        ui.button("Toggle",
                                  variant="outline", size="sm",
                                  on_click=s.toggle())
                        ui.button("Set true",
                                  variant="ghost", size="sm",
                                  on_click=s.set(True))
                        ui.button("Set false",
                                  variant="ghost", size="sm",
                                  on_click=s.set(False))

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "One text slot : ``label=str``. Switch is "
                        "a leaf — no ``with`` block. Reactive "
                        "``checked`` / ``disabled`` bindings ride "
                        "through ``BINDABLE_PROPS``.",
                        color="muted", size="sm",
                    )

                    ui.heading("label=str", level=3)
                    with ui.vstack():
                        ui.switch(label="Plain label")
                        ui.switch(label="With an emoji 🚀",
                                  checked=True)

                    ui.heading(
                        "checked / disabled = ClientBinding — see "
                        "External controls (Card 9)",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Empty label", level=3)
                    ui.switch(label="")

                    ui.heading("Very long label (120 chars)", level=3)
                    ui.switch(label="A" * 120)

                    ui.heading("Emoji + multi-script label", level=3)
                    ui.switch(label="Ship 🚀 — שלום — 中文 — مرحبا")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    ui.switch(label="<script>alert(1)</script>")

                    ui.heading("Default-off vs default-on starting "
                               "state", level=3)
                    with ui.vstack():
                        ui.switch(label="Starts off")
                        ui.switch(label="Starts on", checked=True)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Switch in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Settings panel", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Privacy", level=4)
                            ui.switch(label="Analytics",
                                      checked=True)
                            ui.switch(label="Crash reports",
                                      checked=True)
                            ui.switch(label="Marketing emails")
                            ui.switch(label="Personalised ads")

                    ui.heading("Inside ui.form (autoname pickup)",
                               level=3)
                    with ui.form():
                        with ui.vstack():
                            ui.switch(label="Email digest",
                                      name="email_digest")
                            ui.switch(label="Slack alerts",
                                      name="slack_alerts",
                                      checked=True)
                            ui.button("Save", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Send a weekly summary email"):
                        ui.switch(label="Weekly digest",
                                  checked=True)

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The real ``<input type=\"checkbox\">`` is "
                        "kept in the DOM (just visually hidden) so "
                        "the native checked / unchecked semantics "
                        "reach screen readers AND keyboard works "
                        "out of the box (Space toggles). The "
                        "``<label>`` wraps the input so clicking "
                        "the visible track and the label both "
                        "toggle.",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        ui.switch(label="Tab here, press Space to "
                                        "fire",
                                  on_change=log_change)

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired "
                        "to a control ; the preview AND the emitted "
                        "HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("Three events on Switch (change / "
                            "focus / blur). Each one wires a "
                            "module-level server callable that "
                            "appends a line to the live log.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Switch's ``BINDABLE_PROPS = "
                        "('checked', 'disabled')`` contract. Both "
                        "flip live via ``bz-model`` / "
                        "``bz-attr:disabled`` — no network "
                        "round-trip. Visual axes (color / size) "
                        "stay design-time.",
                        color="muted", size="sm",
                    )
                    client = SwitchClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("checked"):
                            ui.switch(checked=client.checked)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.switch(label="Client-bound switch",
                                   checked=client.checked,
                                   disabled=client.disabled)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-model on checked, "
                        "bz-attr:disabled on disabled.",
                        serialize_html(
                            ui.switch(
                                label="Client-bound switch",
                                checked=client.checked,
                                disabled=client.disabled,
                            )
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (a switch driven from sibling "
                        "buttons) played three ways. Pick the mode "
                        "that fits your need : imperative for purely-"
                        "visual switches, binding when another "
                        "component needs to read the checked state, "
                        "both together when you want write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The switch owns its checked "
                        "flag in client scope. ``.toggle()`` / "
                        "``.set(bool)`` dispatch DOM events caught by "
                        "the switch root. **Use this by default — "
                        "it's the natural style for purely-visual "
                        "state.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md", wrap=True):
                        m1 = ui.switch(label="Imperative")
                        ui.button("Check",
                                  size="sm",
                                  on_click=m1.set(True))
                        ui.button("Uncheck",
                                  variant="ghost", size="sm",
                                  on_click=m1.set(False))
                        ui.button("Toggle",
                                  variant="outline", size="sm",
                                  on_click=m1.toggle())
                        ui.button("Set true",
                                  variant="ghost", size="sm",
                                  on_click=m1.set(True))
                        ui.button("Set false",
                                  variant="ghost", size="sm",
                                  on_click=m1.set(False))

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the checked state** — a "
                        "text that appears when on, a badge that "
                        "mirrors it, server-side awareness on the "
                        "next render. The binding is the single "
                        "source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = SwitchClient(key="binding_only")
                    with ui.hstack(align="center", gap="md"):
                        ui.switch(label="Notifications",
                                  checked=bound.checked)
                        ui.text('Status: on',
                                color="success",
                                visible=bound.checked)
                        ui.text("Status : off",
                                color="muted",
                                visible=~bound.checked)

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        'A binding supplied AND ``.set()`` / '
                            '``.toggle()`` ``.toggle()`` / ``.set(bool)`` '
                            'called on the instance. The framework detects '
                            'the binding and delegates to '
                            '``binding.set(...)`` — **the DOM dispatch is not'
                            ' used**, single source of truth preserved. The '
                            'imperative buttons and the bound value converge '
                            'on the same flag.',
                        color="muted", size="sm",
                    )
                    both = SwitchClient(key="both")
                    with ui.hstack(align="center", gap="md", wrap=True):
                        m3 = ui.switch(label="Bound + imperative",
                                       checked=both.checked)
                        ui.text('Status: on',
                                color="success",
                                visible=both.checked)
                        ui.button("Check via .set(True)",
                                  size="sm",
                                  on_click=m3.set(True))
                        ui.button("Uncheck via .set(False)",
                                  variant="ghost", size="sm",
                                  on_click=m3.set(False))
                        ui.button("Toggle via .toggle()",
                                  variant="outline", size="sm",
                                  on_click=m3.toggle())
                        ui.button("Set true",
                                  variant="ghost", size="sm",
                                  on_click=m3.set(True))

                    ui.divider()

                    preview = ui.switch(label="Live switch",
                                        checked=bound.checked,
                                        color="primary")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-model writes the bound path ; siblings "
                        "read it without a round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Three switches — each event wires an "
                            "client expression that pushes onto a "
                            "ClientState list. Zero network ; the "
                            "log below re-renders via bz-text on "
                            "every push.",
                            color="muted", size="sm")
                    cevents = SwitchClientEvents()
                    # change → push the new boolean ; focus / blur
                    # carry no payload, keep the literal event name.
                    _checked = ClientExpression(
                        "'checked=' + $event.target.checked"
                    )
                    with ui.hstack(wrap=True, gap="lg", justify="center"):
                        ui.switch(label="change",
                                  on_change=cevents.log.push(_checked))
                        ui.switch(label="focus",
                                  on_focus=cevents.log.push("focus"))
                        ui.switch(label="blur",
                                  on_blur=cevents.log.push("blur"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.SwitchClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the "
                        "'change' switch)",
                        serialize_html(
                            ui.switch(label="change",
                                      on_change=cevents.log.push(_checked))
                        ),
                    )
