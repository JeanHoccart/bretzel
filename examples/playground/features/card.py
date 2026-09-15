"""``Card`` test bench.

Seven visual cards : Reference / Edge cases / Composability / A11y /
Server playground / Server events / Client events. ``BINDABLE_PROPS =
()`` so no Client playground card (S5) — Card is a structural
wrapper, mutate the surface via ``visible=`` / conditional render at
the call site. ``EVENTS`` is non-empty though, so Client events (S6)
still applies — gated independently of BINDABLE_PROPS.

Four props (``color`` / ``padding`` / ``hoverable`` / ``href``) plus
three events (click / mouseenter / mouseleave). Polymorphic root :
``<div>`` by default, ``<a>`` when ``href=`` is set (auto-enables
``hoverable``).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/card"


COLORS   = ["surface", "primary", "secondary", "success",
            "warning", "error", "info", "muted"]
PADDINGS = ["none", "xs", "sm", "md", "lg", "xl"]


class CardPlayground(PageState):
    color:        str  = field(default="surface")
    padding:      str  = field(default="md")
    hoverable:    bool = field(default=False)
    href:         str  = field(default="")
    # Escape hatches.
    classes:      str  = field(default="")
    custom_id:    str  = field(default="")
    aria_label:   str  = field(default="")
    style:        str  = field(default="")
    extra_attrs:  str  = field(default="")
    # Universal modifiers.
    visible:      str  = field(default="on")
    tooltip:      str  = field(default="")
    # Event-handler shape.
    on_click_mode: str = field(default="none")  # none | server | client | both


class CardEvents(PageState):
    log: list = field(default_factory=list)


class CardClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = CardEvents()
    state.log = [*state.log, name]


def log_click()       -> None: log("click")
def log_mouseenter()  -> None: log("mouseenter")
def log_mouseleave()  -> None: log("mouseleave")


def clear_log() -> None:
    state = CardEvents()
    state.log = []


def server_changed(state: CardPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[CardPlayground] re-renders server_panel automatically.
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


def build_preview(state: CardPlayground):
    """Build the preview Card with the body baked in.

    Card is a container — we can't return the Card and let the caller
    fill it because the with-block lives here. The function instead
    enters the Card itself and emits the body content.
    """
    kwargs: dict = {
        "color": state.color,
        "padding": state.padding,
        "hoverable": state.hoverable,
    }
    if state.href:
        kwargs["href"] = state.href
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
        kwargs["on_click"] = [playground_click_handler, _CLIENT_CLICK_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[CardPlayground])
def server_panel() -> None:
    state = CardPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("padding"):
            ui.select(value=state.padding,
                      options=[(p, p) for p in PADDINGS],
                      on_change=server_changed)
        with control("hoverable"):
            ui.switch(checked=state.hoverable, on_change=server_changed)
        with control("href (forces <a> tag + hoverable)"):
            ui.input(value=state.href, placeholder="/button",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!ring-2 !ring-primary",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-card",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Project card",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 320px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=card",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Open project",
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

    kwargs = build_preview(state)
    # Two-step : actually render the Card for the preview, then a
    # second time for the inspection block. The body is small.
    with ui.flex(justify="center", align="center"):
        with ui.card(**kwargs):
            ui.heading("Preview card", level=3)
            ui.text("Body content here.", color="muted")

    ui.divider()

    preview_card = ui.card(**kwargs)
    with preview_card:
        ui.heading("Preview card", level=3)
        ui.text("Body content here.", color="muted")
    emitted_html_block(
        "Emitted HTML (with sample body)",
        serialize_html(preview_card),
    )


@refreshable(deps=[CardEvents])
def events_panel() -> None:
    state = CardEvents()

    ui.text(
        "Card supports three events : click / mouseenter / "
        "mouseleave. Each one wires a module-level server callable "
        "that appends a line to the log below.",
        color="muted", size="sm",
    )

    with ui.hstack(wrap=True, justify="center"):
        with ui.card(hoverable=True, on_click=log_click,
                     classes="min-w-32"):
            ui.text("Click me", weight="bold")
        with ui.card(hoverable=True, on_mouseenter=log_mouseenter,
                     classes="min-w-32"):
            ui.text("Hover me — mouseenter", weight="bold")
        with ui.card(hoverable=True, on_mouseleave=log_mouseleave,
                     classes="min-w-32"):
            ui.text("Hover then leave", weight="bold")

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
        ui.text("(no events yet — interact with one of the cards "
                "above to fire its event)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.card(hoverable=True, on_click=log_click)
    with representative:
        ui.text("Click me", weight="bold")
    emitted_html_block(
        "Emitted HTML (the 'click' card)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Card", level=1)
            ui.text(
                "Surface wrapper. ``<div>`` by default ; switches to "
                "``<a>`` when ``href=`` is passed (auto-enabling "
                "``hoverable``). Quick visual reference below ; the "
                "Server playground / Server events cards exercise "
                "every prop and event.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Color", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            with ui.card(color=c, classes="min-w-32"):
                                ui.text(c, weight="bold")

                    ui.heading("Padding", level=3)
                    with ui.hstack(wrap=True, align="end"):
                        for p in PADDINGS:
                            with ui.card(padding=p):
                                ui.text(f"padding={p}")

                    ui.heading("Hoverable", level=3)
                    with ui.hstack():
                        with ui.card():
                            ui.text("Static (default)")
                        with ui.card(hoverable=True):
                            ui.text("Hover me — lifts 1 px")

                    ui.heading("As link (href= → <a> tag + hoverable)",
                               level=3)
                    with ui.hstack():
                        with ui.card(href="/button"):
                            ui.heading("Button page", level=4)
                            ui.text("Click anywhere.", color="muted",
                                    size="sm")
                        with ui.card(href="https://example.com"):
                            ui.heading("External link", level=4)
                            ui.text("Whole card is the target.",
                                    color="muted", size="sm")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge children and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty body", level=3)
                    with ui.hstack():
                        ui.card()  # no with-block — silently empty

                    ui.heading("Single text node (no vstack)", level=3)
                    with ui.card():
                        ui.text("Just text, no structure.")

                    ui.heading("Deeply nested", level=3)
                    with ui.card():
                        with ui.card():
                            with ui.card():
                                ui.text("Three levels deep.",
                                        color="muted", size="sm")

                    ui.heading("href + hoverable=False forced", level=3)
                    ui.text(
                        "``hoverable=`` is explicit-False here even "
                        "though href is set. The component honours "
                        "the override.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        with ui.card(href="/button", hoverable=False):
                            ui.text("Linked but no lift",
                                    color="muted")

                    ui.heading("Very wide content (overflow)", level=3)
                    with ui.card(classes="max-w-sm"):
                        ui.text("A" * 200, truncate=False, color="muted",
                                size="xs")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Card composing with other containers.",
                            color="muted", size="sm")

                    ui.heading("Card inside Card (sub-surface)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Outer card", level=3)
                            with ui.card(color="muted"):
                                ui.text("Inner sub-surface",
                                        color="muted", size="sm")

                    ui.heading("Cards inside grid (responsive list)",
                               level=3)
                    with ui.grid(cols={"base": 1, "sm": 2, "md": 3},
                                 gap="md"):
                        for i in range(1, 7):
                            with ui.card(hoverable=True):
                                ui.heading(f"Project {i}", level=4)
                                ui.text("Click to open.",
                                        color="muted", size="sm")

                    ui.heading("Card with header + body + actions",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.heading("Project Aurora", level=3)
                                ui.badge("Active", color="success")
                            ui.text(
                                "Multi-line body copy talking about "
                                "what this project does and why "
                                "anyone should care.",
                                color="muted",
                            )
                            ui.divider()
                            with ui.hstack(justify="end", gap="sm"):
                                ui.button("Cancel", variant="ghost")
                                ui.button("Save",   color="primary")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "When the card is a link (``href=`` or full-"
                        "card-clickable pattern), screen readers "
                        "announce it as one navigation target. Pair "
                        "with a meaningful ``aria-label`` if the "
                        "visible content doesn't summarise the "
                        "destination.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        with ui.card(href="/button",
                                     aria_label="Open Button reference"):
                            ui.heading("Buttons", level=4)
                            ui.text("Reference and demos",
                                    color="muted", size="sm")

            # ── Card 5 — Server playground ──────────────────────────
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

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("Card supports click / mouseenter / "
                            "mouseleave. Each event wires a server "
                            "callable that appends a line to the "
                            "live log.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 7 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Same three events wired to client "
                        "expressions that push onto a ClientState "
                        "list. Zero network ; the log below "
                        "re-renders via bz-text on every push.",
                        color="muted", size="sm",
                    )
                    cevents = CardClientEvents()
                    with ui.hstack(wrap=True, justify="center"):
                        with ui.card(hoverable=True,
                                     on_click=cevents.log.push("click"),
                                     classes="min-w-32"):
                            ui.text("Click me", weight="bold")
                        with ui.card(
                            hoverable=True,
                            on_mouseenter=cevents.log.push("mouseenter"),
                            classes="min-w-32",
                        ):
                            ui.text("Hover me — mouseenter", weight="bold")
                        with ui.card(
                            hoverable=True,
                            on_mouseleave=cevents.log.push("mouseleave"),
                            classes="min-w-32",
                        ):
                            ui.text("Hover then leave", weight="bold")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.CardClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    representative = ui.card(
                        hoverable=True,
                        on_click=cevents.log.push("click"),
                    )
                    with representative:
                        ui.text("Click me", weight="bold")
                    emitted_html_block(
                        "Emitted HTML (representative — the 'click' card)",
                        serialize_html(representative),
                    )
