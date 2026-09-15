"""``IconButton`` test bench.

Nine visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Server events / Client playground /
Client events. ``BINDABLE_PROPS = ("disabled", "loading")`` — same
shape as Button minus the label (the icon IS the content) ; visual
axes plus the icon itself are design-time.

Five events (click / focus / blur / mouseenter / mouseleave) plus
the loading mutex (Spinner ↔ Icon).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/icon-button"


VARIANTS = ["solid", "soft", "surface", "outline", "ghost"]
SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]
TYPES    = ["button", "submit", "reset"]


class IconButtonPlayground(PageState):
    icon:       str  = field(default="save")
    variant:    str  = field(default="ghost")
    size:       str  = field(default="md")
    color:      str  = field(default="primary")
    disabled:   bool = field(default=False)
    loading:    bool = field(default=False)
    type:       str  = field(default="button")
    # Escape hatches.
    classes:    str  = field(default="")
    custom_id:  str  = field(default="")
    aria_label: str  = field(default="")
    style:      str  = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:    str  = field(default="on")
    tooltip:    str  = field(default="")
    # Event-handler shape.
    on_click_mode: str = field(default="none")


class IconButtonEvents(PageState):
    log: list = field(default_factory=list)


class IconButtonClient(ClientState, persist="memory"):
    """Mirror of IconButton's BINDABLE_PROPS = ('disabled', 'loading')."""

    disabled: bool = field(default=False)
    loading:  bool = field(default=False)


class IconButtonClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = IconButtonEvents()
    state.log = [*state.log, name]


def log_click()       -> None: log("click")
def log_focus()       -> None: log("focus")
def log_blur()        -> None: log("blur")
def log_mouseenter()  -> None: log("mouseenter")
def log_mouseleave()  -> None: log("mouseleave")


def clear_log() -> None:
    state = IconButtonEvents()
    state.log = []


def server_changed(state: IconButtonPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_click_handler() -> None:
    log("playground-server-click")


_CLIENT_CLICK_EXPR = "this.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: IconButtonPlayground):
    kwargs: dict = {
        "variant": state.variant,
        "size": state.size,
        "color": state.color,
        "disabled": state.disabled,
        "loading": state.loading,
        "type": state.type,
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
    if state.on_click_mode == "server":
        kwargs["on_click"] = playground_click_handler
    elif state.on_click_mode == "client":
        kwargs["on_click"] = _CLIENT_CLICK_EXPR
    elif state.on_click_mode == "both":
        kwargs["on_click"] = [playground_click_handler,
                              _CLIENT_CLICK_EXPR]
    return ui.icon_button(state.icon or "save", **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[IconButtonPlayground])
def server_panel() -> None:
    state = IconButtonPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("icon"):
            ui.input(value=state.icon, placeholder="save",
                     on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("type"):
            ui.select(value=state.type,
                      options=[(t, t) for t in TYPES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("loading"):
            ui.switch(checked=state.loading, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-full",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-icon-button",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Save document",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="transform: rotate(15deg)",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=icon-btn",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Save",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_click mode"):
            ui.select(value=state.on_click_mode,
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


@refreshable(deps=[IconButtonEvents])
def events_panel() -> None:
    state = IconButtonEvents()

    with ui.hstack(wrap=True, justify="center"):
        ui.icon_button("mouse-pointer-click", variant="outline",
                       on_click=log_click, aria_label="click")
        ui.icon_button("focus",         variant="outline",
                       on_focus=log_focus, aria_label="focus")
        ui.icon_button("eye-off",       variant="outline",
                       on_blur=log_blur, aria_label="blur")
        ui.icon_button("mouse",         variant="outline",
                       on_mouseenter=log_mouseenter,
                       aria_label="mouseenter")
        ui.icon_button("mouse-off",     variant="outline",
                       on_mouseleave=log_mouseleave,
                       aria_label="mouseleave")

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
        ui.text("(no events yet — interact with one of the icon "
                "buttons above to fire its event)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the 'click' icon button)",
        serialize_html(
            ui.icon_button("mouse-pointer-click",
                           variant="outline",
                           on_click=log_click,
                           aria_label="click")
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Icon button", level=1)
            ui.text(
                "Square button whose content is a single icon. Same "
                "visual identity as Button (variants / sizes / focus "
                "ring) but the icon is positional and "
                "``aria_label=`` is required for a11y. The Server "
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

                    ui.heading("Variants", level=3)
                    with ui.hstack():
                        for v in VARIANTS:
                            ui.icon_button("save", variant=v,
                                           aria_label=f"{v} save")

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="end"):
                        for s in SIZES:
                            ui.icon_button("save", size=s,
                                           aria_label=f"{s} save")

                    ui.heading("Colors (solid)", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.icon_button("circle", variant="solid",
                                           color=c,
                                           aria_label=c)

                    ui.heading("Disabled", level=3)
                    with ui.hstack():
                        ui.icon_button("save", aria_label="Enabled")
                        ui.icon_button("save", disabled=True,
                                       aria_label="Disabled")

                    ui.heading("Loading", level=3)
                    with ui.hstack():
                        ui.icon_button("save", aria_label="Idle")
                        ui.icon_button("save", loading=True,
                                       aria_label="In flight")

                    ui.heading("Type (no visual variation — behavioural)",
                               level=3)
                    with ui.hstack():
                        ui.icon_button("save", type="button",
                                       aria_label="Button")
                        ui.icon_button("save", type="submit",
                                       aria_label="Submit")
                        ui.icon_button("save", type="reset",
                                       aria_label="Reset")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``icon`` is the positional slot. Accepts a "
                        "str shortcut (Iconify name, auto-wrapped in "
                        "``ui.icon``) OR a fully-built ``ui.icon(...)`` "
                        "Component for fine-tuned colour / style.",
                        color="muted", size="sm",
                    )

                    ui.heading("icon=str (shortcut)", level=3)
                    with ui.hstack(wrap=True):
                        ui.icon_button("save", aria_label="Save")
                        ui.icon_button("trash-2", color="error",
                                       aria_label="Delete")
                        ui.icon_button("settings", variant="outline",
                                       aria_label="Settings")

                    ui.heading("icon=Component (full override)", level=3)
                    with ui.hstack(wrap=True):
                        ui.icon_button(
                            ui.icon("heart", color="error"),
                            variant="outline",
                            aria_label="Like",
                        )
                        ui.icon_button(
                            ui.icon("star", set="phosphor", icon_style="fill"),
                            variant="ghost", color="warning",
                            aria_label="Favourite",
                        )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("No icon (empty string)", level=3)
                    ui.icon_button("",
                                   aria_label="Empty icon — visible "
                                              "as a bare square")

                    ui.heading("Invalid icon name (silent fallback)",
                               level=3)
                    ui.icon_button("this-icon-does-not-exist",
                                   aria_label="Invalid icon — square "
                                              "remains")

                    ui.heading("Loading + disabled together", level=3)
                    ui.icon_button("save", loading=True, disabled=True,
                                   aria_label="Stuck")

                    ui.heading("Very large via classes", level=3)
                    ui.icon_button("save", size="xl",
                                   classes="!h-16 !w-16",
                                   aria_label="Big save")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("IconButton nested inside common "
                            "containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.hstack():
                        with ui.tooltip("Save document"):
                            ui.icon_button("save", aria_label="Save")
                        with ui.tooltip("Delete row"):
                            ui.icon_button("trash-2", color="error",
                                           aria_label="Delete")
                        with ui.tooltip("Settings"):
                            ui.icon_button("settings", variant="outline",
                                           aria_label="Settings")

                    ui.heading("In a toolbar (hstack)", level=3)
                    with ui.card(padding="sm"):
                        with ui.hstack(gap="sm"):
                            ui.icon_button("bold",      aria_label="Bold")
                            ui.icon_button("italic",    aria_label="Italic")
                            ui.icon_button("underline", aria_label="Underline")
                            ui.divider(orientation="vertical")
                            ui.icon_button("align-left",
                                           aria_label="Align left")
                            ui.icon_button("align-center",
                                           aria_label="Align center")
                            ui.icon_button("align-right",
                                           aria_label="Align right")

                    ui.heading("Inside ui.card (action chrome)",
                               level=3)
                    with ui.card():
                        with ui.hstack(justify="between",
                                       align="center"):
                            ui.text("Project Aurora", weight="bold")
                            with ui.hstack(gap="xs"):
                                ui.icon_button("edit",
                                               variant="ghost",
                                               aria_label="Edit")
                                ui.icon_button("trash-2",
                                               variant="ghost",
                                               color="error",
                                               aria_label="Delete")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "An icon-only button is invisible to screen "
                        "readers without an ``aria_label``. The "
                        "framework lets you skip it (no hard error) "
                        "but every demo above passes one — the "
                        "playground itself is a constant reminder.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        ui.icon_button("keyboard",
                                       on_click=log_click,
                                       aria_label="Press Space to fire")

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
                    ui.text("Every event of IconButton "
                            "(click / focus / blur / mouseenter / "
                            "mouseleave) is wired to a module-level "
                            "callable that appends a line to the "
                            "live log.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of IconButton's ``BINDABLE_PROPS = "
                        "('disabled', 'loading')`` contract. the runtime "
                        "mutates disabled in-browser ; loading "
                        "swaps the spinner ↔ icon mutex via "
                        "bz-show + a pre-stamped display:none.",
                        color="muted", size="sm",
                    )
                    client = IconButtonClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("disabled"):
                            ui.switch(checked=client.disabled)
                        with control("loading"):
                            ui.switch(checked=client.loading)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.icon_button(
                            "save",
                            disabled=client.disabled,
                            loading=client.loading,
                            aria_label="Save (client-bound)",
                        )

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-attr:disabled on the "
                        "&lt;button&gt;, mutex spinner ↔ icon via "
                        "bz-show + a pre-stamped display:none.",
                        serialize_html(
                            ui.icon_button(
                                "save",
                                disabled=client.disabled,
                                loading=client.loading,
                                aria_label="Save",
                            )
                        ),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Five icon buttons — each event wires "
                            "a client expression that pushes onto "
                            "a ClientState list. Zero network ; "
                            "the log below re-renders via bz-text "
                            "on every push.",
                            color="muted", size="sm")
                    cevents = IconButtonClientEvents()
                    with ui.hstack(wrap=True, justify="center"):
                        ui.icon_button(
                            "mouse-pointer-click",
                            variant="outline",
                            on_click=cevents.log.push("click"),
                            aria_label="click",
                        )
                        ui.icon_button(
                            "focus",
                            variant="outline",
                            on_focus=cevents.log.push("focus"),
                            aria_label="focus",
                        )
                        ui.icon_button(
                            "eye-off",
                            variant="outline",
                            on_blur=cevents.log.push("blur"),
                            aria_label="blur",
                        )
                        ui.icon_button(
                            "mouse",
                            variant="outline",
                            on_mouseenter=cevents.log.push("mouseenter"),
                            aria_label="mouseenter",
                        )
                        ui.icon_button(
                            "mouse-off",
                            variant="outline",
                            on_mouseleave=cevents.log.push("mouseleave"),
                            aria_label="mouseleave",
                        )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.IconButtonClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the "
                        "'click' icon button)",
                        serialize_html(
                            ui.icon_button(
                                "mouse-pointer-click",
                                variant="outline",
                                on_click=cevents.log.push("click"),
                                aria_label="click",
                            )
                        ),
                    )
