"""``Checkbox`` test bench.

Ten cards : full 7-section gabarit (S2 split into 4 visual cards).
``BINDABLE_PROPS = ("checked", "disabled")`` — both get a dedicated
Client playground card ; visual axes (size / color) stay design-time.

Eight props : ``checked`` / ``name`` (autoname from ``checked``) /
``value`` / ``label`` / ``disabled`` / ``required`` / ``color`` /
``size``. Three events : ``change`` / ``focus`` / ``blur``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/checkbox"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class CheckboxPlayground(PageState):
    checked:     bool = field(default=False)
    label:       str  = field(default="Subscribe to updates")
    value:       str  = field(default="")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
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


class CheckboxEvents(PageState):
    log: list = field(default_factory=list)


class CheckboxClient(ClientState, persist="memory"):
    """Mirror of Checkbox's BINDABLE_PROPS = ('checked', 'disabled')."""

    checked:  bool = field(default=False)
    disabled: bool = field(default=False)


class CheckboxClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# Drives the "Inside ui.form (autoname pickup)" demo in Composability.
# Each field_name flows through AUTONAME_FROM="checked" → the form-data
# keys are ``subscribe`` and ``security``. No manual ``name=`` anywhere.
class CheckboxFormDemo(ClientState, persist="memory"):
    subscribe: bool = field(default=False)
    security:  bool = field(default=True)


def log(name: str) -> None:
    state = CheckboxEvents()
    state.log = [*state.log, name]


def log_change()  -> None: log("change")
def log_focus()   -> None: log("focus")
def log_blur()    -> None: log("blur")


def clear_log() -> None:
    state = CheckboxEvents()
    state.log = []


def server_changed(state: CheckboxPlayground) -> None:
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


def build_preview(state: CheckboxPlayground):
    kwargs: dict = {
        "checked": state.checked,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
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
    return ui.checkbox(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[CheckboxPlayground])
def server_panel() -> None:
    state = CheckboxPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("checked"):
            ui.switch(checked=state.checked, on_change=server_changed)
        with control("label"):
            ui.input(value=state.label,
                     placeholder="Subscribe to updates",
                     on_change=server_changed)
        with control("value (form submission)"):
            ui.input(value=state.value, placeholder="yes",
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
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-4",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-checkbox",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Subscribe consent",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="margin-top: 4px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=checkbox",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="We'll only email releases",
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


@refreshable(deps=[CheckboxEvents])
def events_panel() -> None:
    state = CheckboxEvents()

    with ui.hstack(wrap=True, gap="lg", justify="center"):
        ui.checkbox(label="change",
                    on_change=log_change)
        ui.checkbox(label="focus",
                    on_focus=log_focus)
        ui.checkbox(label="blur",
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
        ui.text("(no events yet — toggle one of the checkboxes "
                "above to fire its event)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the 'change' checkbox)",
        serialize_html(
            ui.checkbox(label="change", on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Checkbox", level=1)
            ui.text(
                "Boolean toggle input with V1's soft-tick identity. "
                "The real ``<input type=\"checkbox\">`` is hidden "
                "(sr-only) and a styled overlay fakes the visual ; "
                "keyboard / screen-reader path stays native. Three "
                "ways to drive the checked state : native click "
                "(simplest), ``c.toggle() / .set(bool)`` imperative "
                "API (default for purely-visual checkboxes), or "
                "``checked=ClientBinding`` "
                "(when another component needs to read or react to "
                "the state). The 3 modes are compared side-by-side "
                "in Card 9.",
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
                            ui.checkbox(label=s, size=s)

                    ui.heading("Colors (when checked)", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.checkbox(label=c.title(),
                                        color=c, checked=True)

                    ui.heading("State", level=3)
                    with ui.vstack():
                        ui.checkbox(label="Unchecked")
                        ui.checkbox(label="Checked", checked=True)
                        ui.checkbox(label="Disabled", disabled=True)
                        ui.checkbox(label="Disabled + checked",
                                    disabled=True, checked=True)
                        ui.checkbox(label="Required", required=True)

                    ui.heading("Without label", level=3)
                    with ui.hstack(gap="lg"):
                        ui.checkbox()
                        ui.checkbox(checked=True)
                        ui.checkbox(disabled=True)

                    ui.heading(
                        "Basic — external triggers via .toggle() "
                        "/ .set(bool)",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance via ``c = ui.checkbox"
                        "(...)`` and call ``c.toggle()`` or "
                        "``c.set(bool)`` from sibling buttons. No "
                        "ClientState declared — the checkbox owns "
                        "its checked flag in client scope and the "
                        "imperative methods dispatch DOM events on "
                        "its root. **This is the default style for "
                        "purely-visual checkboxes.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md", wrap=True):
                        c = ui.checkbox(label="Driven externally")
                        ui.button("Toggle",
                                  variant="outline",
                                  on_click=c.toggle())
                        ui.button("Set true",
                                  variant="ghost",
                                  on_click=c.set(True))
                        ui.button("Set false",
                                  variant="ghost",
                                  on_click=c.set(False))

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "One text slot : ``label=str``. Checkbox is "
                        "a leaf — no ``with`` block, no Component "
                        "label override. Reactive ``checked`` / "
                        "``disabled`` bindings ride through "
                        "``BINDABLE_PROPS``.",
                        color="muted", size="sm",
                    )

                    ui.heading("label=str", level=3)
                    with ui.vstack():
                        ui.checkbox(label="Plain label")
                        ui.checkbox(label="With an emoji 🚀")

                    ui.heading(
                        "checked / disabled = ClientBinding — see "
                        "External controls card",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Empty label", level=3)
                    ui.checkbox(label="")

                    ui.heading("Very long label (120 chars)", level=3)
                    ui.checkbox(label="A" * 120)

                    ui.heading("Emoji + multi-script label", level=3)
                    ui.checkbox(label="Ship 🚀 — שלום — 中文 — مرحبا")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    ui.checkbox(label="<script>alert(1)</script>")

                    ui.heading("Disabled + required (consent-form "
                               "anti-pattern)", level=3)
                    ui.text(
                        "Locked but still flagged required — the "
                        "browser will block submission. Framework "
                        "honours both flags.",
                        color="muted", size="xs",
                    )
                    ui.checkbox(label="Locked but required",
                                disabled=True, required=True)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Checkbox in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.form (autoname pickup)",
                               level=3)
                    ui.text(
                        "``AUTONAME_FROM=\"checked\"`` lets the "
                        "checkbox derive its ``name=`` from the bound "
                        "state's ``field_name`` automatically — no "
                        "manual ``name=`` wiring needed. The form "
                        "below has each checkbox bound to a "
                        "``CheckboxFormDemo`` field ; submit POSTs "
                        "the form-data with the field names as keys.",
                        color="muted", size="xs",
                    )
                    form_state = CheckboxFormDemo()
                    with ui.form():
                        with ui.vstack():
                            ui.checkbox(label="Subscribe to releases",
                                        checked=form_state.subscribe)
                            ui.checkbox(label="Subscribe to security "
                                              "advisories",
                                        checked=form_state.security)
                            ui.button("Save", type="submit",
                                      color="primary")

                    ui.heading("List of options (settings panel)",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Notification preferences",
                                       level=4)
                            ui.checkbox(label="Email",  checked=True)
                            ui.checkbox(label="Slack")
                            ui.checkbox(label="SMS",   disabled=True)
                            ui.checkbox(label="Push")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("We'll only send releases — "
                                    "never marketing"):
                        ui.checkbox(label="Subscribe to releases")

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
                        "``<label>`` wraps the input so clicking the "
                        "visible box and the label both toggle.",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        ui.checkbox(label="Tab here, press Space to "
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
                    ui.text("Three events on Checkbox (change / "
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
                        "Mirror of Checkbox's ``BINDABLE_PROPS = "
                        "('checked', 'disabled')`` contract. Both "
                        "flip live via ``bz-model`` / "
                        "``bz-attr:disabled`` — no network "
                        "round-trip. Visual axes (color / size) "
                        "stay design-time.",
                        color="muted", size="sm",
                    )
                    client = CheckboxClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("checked"):
                            ui.switch(checked=client.checked)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.checkbox(label="Client-bound checkbox",
                                    checked=client.checked,
                                    disabled=client.disabled)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-model on checked, "
                        "bz-attr:disabled on disabled.",
                        serialize_html(
                            ui.checkbox(
                                label="Client-bound checkbox",
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
                        "Same scenario (sibling buttons drive a "
                        "checkbox) played three ways. Pick the mode "
                        "that fits your need : imperative for "
                        "purely-visual checkboxes, binding when "
                        "another component needs to read the "
                        "checked state, both together when you want "
                        "write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The checkbox owns its "
                        "checked flag in client scope. ``.toggle()`` "
                        "/ "
                        "``.set(bool)`` dispatch DOM events caught "
                        "by the checkbox root. **Use this by default "
                        "for checkboxes — it's the natural style "
                        "for purely-visual state.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md", wrap=True):
                        m1 = ui.checkbox(label="Imperative only")
                        ui.button("Check", on_click=m1.set(True))
                        ui.button("Uncheck",
                                  variant="outline",
                                  on_click=m1.set(False))
                        ui.button("Toggle",
                                  variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set true",
                                  variant="ghost",
                                  on_click=m1.set(True))
                        ui.button("Set false",
                                  variant="ghost",
                                  on_click=m1.set(False))

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the checked state** — a "
                        "second checkbox that mirrors it, a label "
                        "that appears when it's checked, a badge "
                        "coloured conditionally. The binding is the "
                        "single source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = CheckboxClient(key="binding_only")
                    with ui.hstack(align="center", gap="md", wrap=True):
                        ui.checkbox(label="I accept the terms",
                                    checked=bound.checked)
                        ui.checkbox(label="(mirror — same binding)",
                                    checked=bound.checked)
                        ui.text("✓ Accepted",
                                visible=bound.checked,
                                color="success", size="sm")

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        "Binding fournie ET on appelle ``.set()`` / "
                        "``.toggle()`` "
                        "/ ``.set(bool)`` / ``.toggle()`` sur "
                        "l'instance. Le framework détecte la "
                        "binding et délègue à ``binding.set(...)`` "
                        "— **le DOM dispatch n'est pas utilisé**, "
                        "single source of truth préservée. Le "
                        "checkbox-mirror et les boutons impératifs "
                        "convergent sur le même flag.",
                        color="muted", size="sm",
                    )
                    both = CheckboxClient(key="both")
                    with ui.hstack(align="center", gap="md", wrap=True):
                        m3 = ui.checkbox(label="Bound + driven",
                                         checked=both.checked)
                        ui.checkbox(label="(mirror)",
                                    checked=both.checked)
                        ui.button("Check", on_click=m3.set(True))
                        ui.button("Uncheck",
                                  variant="outline",
                                  on_click=m3.set(False))
                        ui.button("Toggle",
                                  variant="outline",
                                  on_click=m3.toggle())
                        ui.button("Set true",
                                  variant="ghost",
                                  on_click=m3.set(True))

                    ui.divider()

                    preview = ui.checkbox(label="Bound checkbox",
                                          checked=bound.checked)
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-model reads + writes the bound path ; "
                        "toggle / set on the binding converge "
                        "without a round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Three checkboxes — each event wires "
                            "a client expression that pushes onto "
                            "a ClientState list. Zero network ; "
                            "the log below re-renders via bz-text "
                            "on every push.",
                            color="muted", size="sm")
                    cevents = CheckboxClientEvents()
                    # change → push the new boolean (target.checked) ;
                    # focus / blur carry no payload, push the literal
                    # event name so the log still reads sensibly.
                    _checked = ClientExpression(
                        "'checked=' + $event.target.checked"
                    )
                    with ui.hstack(wrap=True, gap="lg", justify="center"):
                        ui.checkbox(label="change",
                                    on_change=cevents.log.push(_checked))
                        ui.checkbox(label="focus",
                                    on_focus=cevents.log.push("focus"))
                        ui.checkbox(label="blur",
                                    on_blur=cevents.log.push("blur"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.CheckboxClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the "
                        "'change' checkbox)",
                        serialize_html(
                            ui.checkbox(label="change",
                                        on_change=cevents.log.push(_checked))
                        ),
                    )
