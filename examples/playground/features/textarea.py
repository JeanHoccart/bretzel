"""``Textarea`` test bench.

Ten cards : full 7-section gabarit (S2 split into 4 visual cards).
``BINDABLE_PROPS = ("value", "disabled", "readonly")`` — all three get
a dedicated Client playground card ; visual axes (size / color / rows)
stay design-time.

Eleven props : ``value`` (autoname-from) / ``name`` / ``placeholder``
/ ``rows`` / ``disabled`` / ``readonly`` / ``required`` /
``minlength`` / ``maxlength`` / ``color`` / ``size``. Six events :
``change`` / ``input`` / ``focus`` / ``blur`` / ``keydown`` /
``keyup``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/textarea"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class TextareaPlayground(PageState):
    value:       str  = field(default="")
    name:        str  = field(default="")
    placeholder: str  = field(default="Type a message…")
    rows:        int  = field(default=4)
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    readonly:    bool = field(default=False)
    required:    bool = field(default=False)
    minlength:   int  = field(default=0)
    maxlength:   int  = field(default=0)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    # Event-handler shape (one toggle covers them all).
    on_change_mode: str = field(default="none")


class TextareaEvents(PageState):
    log: list = field(default_factory=list)


class TextareaClient(ClientState, persist="memory"):
    """Mirror of Textarea's BINDABLE_PROPS."""

    value:    str  = field(default="Live two-way bound — type here")
    disabled: bool = field(default=False)
    readonly: bool = field(default=False)


class TextareaClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = TextareaEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    log(f"change(value[:30]={value[:30]!r})")


def log_input(value: str = "") -> None:
    log(f"input(value[:30]={value[:30]!r})")


def log_focus()    -> None: log("focus")
def log_blur()     -> None: log("blur")
def log_keydown()  -> None: log("keydown")
def log_keyup()    -> None: log("keyup")


def clear_log() -> None:
    state = TextareaEvents()
    state.log = []


def server_changed(state: TextareaPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value[:30]={value[:30]!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: TextareaPlayground):
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "rows": int(state.rows or 4),
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "readonly": state.readonly,
        "required": state.required,
    }
    if int(state.minlength or 0) > 0:
        kwargs["minlength"] = int(state.minlength)
    if int(state.maxlength or 0) > 0:
        kwargs["maxlength"] = int(state.maxlength)
    if state.name:
        kwargs["name"] = state.name
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
    return ui.textarea(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[TextareaPlayground])
def server_panel() -> None:
    state = TextareaPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.textarea(value=state.value, rows=3,
                        on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="message",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder,
                     placeholder="Type a message…",
                     on_change=server_changed)
        with control("rows (initial height)"):
            ui.number_input(value=state.rows,
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
        with control("readonly"):
            ui.switch(checked=state.readonly, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("minlength (0 = none)"):
            ui.number_input(value=state.minlength,
                     on_change=server_changed)
        with control("maxlength (0 = none)"):
            ui.number_input(value=state.maxlength,
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!resize-none",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-textarea",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Comment",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="font-family: monospace",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=textarea",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Leave a comment",
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


@refreshable(deps=[TextareaEvents])
def events_panel() -> None:
    state = TextareaEvents()

    with ui.vstack():
        ui.textarea(placeholder="change handler", rows=2,
                    on_change=log_change)
        ui.textarea(placeholder="input handler (per keystroke)",
                    rows=2, on_input=log_input)
        ui.textarea(placeholder="focus handler", rows=2,
                    on_focus=log_focus)
        ui.textarea(placeholder="blur handler", rows=2,
                    on_blur=log_blur)
        ui.textarea(placeholder="keydown handler", rows=2,
                    on_keydown=log_keydown)
        ui.textarea(placeholder="keyup handler", rows=2,
                    on_keyup=log_keyup)

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
        ui.text("(no events yet — interact with one of the "
                "textareas above)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the 'change' textarea)",
        serialize_html(
            ui.textarea(placeholder="change handler",
                        rows=2, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Textarea", level=1)
            ui.text(
                "Multi-line text input. Visually identical to "
                "``ui.input`` but renders a ``<textarea>`` and "
                "exposes a ``rows=`` prop for the initial height. "
                "Two-way bind via ``bz-model`` when ``value`` is a "
                "ClientBinding. The Server playground card stress-"
                "tests every prop ; the emitted HTML is shown live "
                "underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading(
                        "Basic — external controls via .set() / "
                        ".clear() / .focus() / .blur()",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance via ``t = ui.textarea(…)`` "
                        "and call ``t.set(value)`` / ``t.clear()`` / "
                        "``t.focus()`` / ``t.blur()`` from a sibling "
                        "button. No ClientState declared — the textarea "
                        "owns its value, sibling buttons drive it via "
                        "DOM dispatch.",
                        color="muted", size="sm",
                    )
                    t = ui.textarea(
                        placeholder="External controls drive me…",
                        rows=3,
                    )
                    with ui.hstack(gap="sm"):
                        ui.button(
                            "Set example text",
                            on_click=t.set("Hello from .set() !\n"
                                           "Multiple lines work."),
                        )
                        ui.button(
                            "Clear",
                            variant="outline",
                            on_click=t.clear(),
                        )
                        ui.button(
                            "Focus",
                            variant="ghost",
                            on_click=t.focus(),
                        )
                        ui.button(
                            "Blur",
                            variant="ghost",
                            on_click=t.blur(),
                        )

                    ui.heading("Rows (initial height)", level=3)
                    with ui.vstack():
                        for r in (2, 4, 6, 10):
                            ui.textarea(rows=r,
                                        placeholder=f"rows={r}")

                    ui.heading("Sizes", level=3)
                    with ui.vstack():
                        for s in SIZES:
                            ui.textarea(size=s,
                                        placeholder=f"size={s}",
                                        rows=2)

                    ui.heading("Colors (focus ring)", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.textarea(color=c,
                                        placeholder=f"color={c}",
                                        rows=2)

                    ui.heading("State", level=3)
                    with ui.vstack():
                        ui.textarea(placeholder="Enabled", rows=2)
                        ui.textarea(placeholder="Disabled",
                                    disabled=True, rows=2)
                        ui.textarea(placeholder="Readonly",
                                    value="Read-only content",
                                    readonly=True, rows=2)
                        ui.textarea(placeholder="Required *",
                                    required=True, rows=2)

                    ui.heading("min/max length", level=3)
                    ui.textarea(placeholder="Between 10 and 200 chars",
                                minlength=10, maxlength=200, rows=3)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Textarea is a leaf — no ``with`` block, no "
                        "child slots. Reactive ``value`` / "
                        "``disabled`` / ``readonly`` bindings ride "
                        "through ``BINDABLE_PROPS``.",
                        color="muted", size="sm",
                    )

                    ui.heading("value=str (pre-fill)", level=3)
                    ui.textarea(value="Pre-filled multi-line "
                                      "content\nfrom the server",
                                rows=3)

                    ui.text(
                        "``value`` / ``disabled`` / ``readonly`` "
                        "accept ClientBinding — see Card 8 (Client "
                        "playground) below for the live binding demo.",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Empty value", level=3)
                    ui.textarea(rows=2)

                    ui.heading("Very large initial content", level=3)
                    ui.textarea(value=("A" * 80 + "\n") * 20, rows=4)

                    ui.heading("Emoji + multi-script content", level=3)
                    ui.textarea(value="Ship 🚀 — שלום — 中文 — "
                                      "مرحبا — π ≈ 3.14",
                                rows=2)

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes — the script renders as "
                        "literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.textarea(value="<script>alert(1)</script>",
                                rows=2)

                    ui.heading("Locked AND required", level=3)
                    ui.text(
                        "Browser blocks submission ; framework "
                        "honours both flags.",
                        color="muted", size="xs",
                    )
                    ui.textarea(value="Locked content",
                                disabled=True, required=True,
                                rows=2)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Textarea in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.form", level=3)
                    with ui.form():
                        with ui.vstack():
                            ui.textarea(name="message",
                                        placeholder="Your message",
                                        rows=4, required=True)
                            ui.button("Send", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.form_field (label + hint)",
                               level=3)
                    with ui.form_field(label="Comment",
                                       hint="Markdown supported"):
                        ui.textarea(name="comment",
                                    placeholder="Leave a comment…",
                                    rows=4)

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Be concise — first impressions "
                                    "matter"):
                        ui.textarea(placeholder="Bio…",
                                    maxlength=160, rows=3)

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Native ``<textarea>`` semantics carry "
                        "through — screen readers announce the "
                        "field type and read pre-filled content. "
                        "Pair with ``aria_label=`` when there's no "
                        "visible label, or wrap in a ``ui."
                        "form_field`` for a visible one.",
                        color="muted", size="sm",
                    )
                    ui.textarea(placeholder="Tab here, type, "
                                            "Tab-out to fire blur",
                                aria_label="A11y demo textarea",
                                on_blur=log_blur, rows=3)

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
                    ui.text("Six events on Textarea (change / input "
                            "/ focus / blur / keydown / keyup). Each "
                            "one wires a module-level server "
                            "callable that appends a line to the "
                            "live log. ``input`` fires per keystroke "
                            "— easy to spam, useful for debounced "
                            "auto-save patterns.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Textarea's ``BINDABLE_PROPS = "
                        "('value', 'disabled', 'readonly')`` contract. "
                        "All three flip live via ``bz-model`` / "
                        "``bz-attr:disabled`` / ``bz-attr:readonly`` — "
                        "no network round-trip. Visual axes (size / "
                        "color / rows) stay design-time.",
                        color="muted", size="sm",
                    )
                    client = TextareaClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("value"):
                            ui.input(value=client.value)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)
                        with control("readonly"):
                            ui.switch(checked=client.readonly)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.textarea(value=client.value,
                                    disabled=client.disabled,
                                    readonly=client.readonly)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-model on value, "
                        "bz-attr:disabled on disabled, "
                        "bz-attr:readonly on readonly.",
                        serialize_html(
                            ui.textarea(value=client.value,
                                        disabled=client.disabled,
                                        readonly=client.readonly)
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (external buttons set / clear "
                        "the textarea) played three ways. Pick the mode "
                        "that fits your need : imperative for purely-"
                        "visual triggers, binding when another component "
                        "needs to read or react to the value, both "
                        "together when you want write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The textarea owns its value "
                        "in the DOM. ``.set()`` / ``.clear()`` dispatch "
                        "DOM events caught by the textarea's own "
                        "``@bz-*`` listeners. ``.focus()`` / "
                        "``.blur()`` are direct DOM calls by id. **Use "
                        "this by default for purely-visual write-only "
                        "control — no other component needs the value.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.textarea(
                        placeholder="Imperative — no ClientState",
                        rows=3,
                    )
                    with ui.hstack(gap="sm"):
                        ui.button(
                            "Set",
                            on_click=m1.set("Set via Mode 1 (imperative)."),
                        )
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the value** — a sibling "
                        "input that mirrors it, a client expression "
                        "that derives from it, server-side awareness "
                        "on the next render. The binding is the "
                        "single source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = TextareaClient(key="binding_only")
                    ui.textarea(value=bound.value, rows=3)
                    with ui.hstack(gap="sm"):
                        ui.button(
                            "Set via binding.set(...)",
                            on_click=bound.value.set(
                                "Set via binding write-through."
                            ),
                        )
                        ui.button(
                            "Clear via binding.set('')",
                            variant="outline",
                            on_click=bound.value.set(""),
                        )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        "Binding fournie ET on appelle ``.set()`` / "
                        "``.clear()`` sur l'instance. Le framework "
                        "détecte la binding et délègue à "
                        "``binding.set(...)`` — **le DOM dispatch "
                        "n'est pas utilisé**, single source of truth "
                        "préservée. Les boutons impératifs et le "
                        "textarea miroir convergent sur le même "
                        "champ.",
                        color="muted", size="sm",
                    )
                    both = TextareaClient(key="both")
                    with control("mirror (also bound)"):
                        ui.textarea(value=both.value, rows=3)
                    m3 = ui.textarea(value=both.value,
                                     placeholder="Bound + imperative",
                                     rows=3)
                    with ui.hstack(gap="sm"):
                        ui.button(
                            "Set via t.set(...)",
                            on_click=m3.set(
                                "Set via Mode 3 (write-through)."
                            ),
                        )
                        ui.button("Clear via t.clear()",
                                  variant="outline",
                                  on_click=m3.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m3.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m3.blur())

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-model reads the bound path ; binding.set "
                        "writes back without a round-trip.",
                        serialize_html(
                            ui.textarea(value=bound.value,
                                        placeholder="Bound textarea",
                                        rows=3)
                        ),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Six textareas — each event wires an "
                            "client expression that pushes onto a "
                            "ClientState list. Zero network ; the "
                            "log below re-renders via bz-text on "
                            "every push.",
                            color="muted", size="sm")
                    cevents = TextareaClientEvents()
                    # For value-bearing events, push the current text
                    # snippet ; for key events push the pressed key.
                    _val = ClientExpression(
                        "'value=' + $event.target.value"
                    )
                    _key = ClientExpression(
                        "'key=' + $event.key"
                    )
                    with ui.vstack():
                        ui.textarea(placeholder="change",
                                    rows=2,
                                    on_change=cevents.log.push(_val))
                        ui.textarea(placeholder="input (per keystroke)",
                                    rows=2,
                                    on_input=cevents.log.push(_val))
                        ui.textarea(placeholder="focus",
                                    rows=2,
                                    on_focus=cevents.log.push("focus"))
                        ui.textarea(placeholder="blur",
                                    rows=2,
                                    on_blur=cevents.log.push("blur"))
                        ui.textarea(placeholder="keydown",
                                    rows=2,
                                    on_keydown=cevents.log.push(_key))
                        ui.textarea(placeholder="keyup",
                                    rows=2,
                                    on_keyup=cevents.log.push(_key))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.TextareaClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the "
                        "'change' textarea). The native ``change`` "
                        "fires on blur after edit ; the client "
                        "expression pushes the new text.",
                        serialize_html(
                            ui.textarea(placeholder="change",
                                        rows=2,
                                        on_change=cevents.log.push(_val))
                        ),
                    )
