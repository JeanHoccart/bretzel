"""``Alert`` test bench.

Nine visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Server events / Client playground /
Client events. ``BINDABLE_PROPS = ("title", "message", "dismissible")``
— the text and the dismissibility flag are bindable ; color stays
design-time (status colour is usually decided at SSR time based on
server state).

Five props (``color`` / ``icon`` / ``title`` / ``dismissible`` /
``message`` positional) plus one event (``dismiss``).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/alert"


COLORS = ["info", "success", "warning", "error",
          "primary", "secondary", "muted"]


class AlertPlayground(PageState):
    message:     str  = field(default="Heads up — this is an alert.")
    color:       str  = field(default="info")
    title:       str  = field(default="")
    icon:        str  = field(default="")     # "" = auto-pick for semantic colors
    dismissible: bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class AlertEvents(PageState):
    log: list = field(default_factory=list)


class AlertClient(ClientState, persist="memory"):
    """Mirror of Alert's BINDABLE_PROPS."""

    title:       str  = field(default="Live title")
    message:     str  = field(default="Live message body — edit me.")


class AlertClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = AlertEvents()
    state.log = [*state.log, name]


def log_close() -> None: log("close")


def clear_log() -> None:
    state = AlertEvents()
    state.log = []


def server_changed(state: AlertPlayground) -> None:
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


def build_preview(state: AlertPlayground):
    kwargs: dict = {
        "color": state.color,
        "dismissible": state.dismissible,
    }
    if state.title:
        kwargs["title"] = state.title
    if state.icon:
        kwargs["icon"] = state.icon
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
    return ui.alert(state.message, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[AlertPlayground])
def server_panel() -> None:
    state = AlertPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("message"):
            ui.textarea(value=state.message, rows=3,
                        on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("title (optional)"):
            ui.input(value=state.title,
                     placeholder="Saved",
                     on_change=server_changed)
        with control("icon (empty = auto-pick)"):
            ui.input(value=state.icon,
                     placeholder="bell / lightbulb",
                     on_change=server_changed)
        with control("dismissible"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!border-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-alert",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Save confirmation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 480px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="role=alert\ndata-test=alert",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Important notice",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="stretch", classes="min-h-16"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[AlertEvents])
def events_panel() -> None:
    state = AlertEvents()

    ui.text(
        "Alert exposes a single event : ``on_close`` fires when "
        "the dismiss icon-button is clicked. The visual close is "
        "client-side ; the handler is for follow-up server work "
        "(mark notification read, ack, etc.).",
        color="muted", size="sm",
    )

    ui.alert(
        "Click the × on the right — the handler logs to the panel "
        "below AND the alert collapses.",
        color="info", dismissible=True, on_close=log_close,
    )

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
        ui.text("(no events yet — dismiss the alert above)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (dismissible alert with on_close handler)",
        serialize_html(
            ui.alert("Sample", color="info", dismissible=True,
                     on_close=log_close)
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Alert", level=1)
            ui.text(
                "Inline status panel. Four semantic colours "
                "(info / success / warning / error) auto-pick an "
                "icon ; pass ``icon=`` to override. Pass "
                "``dismissible=True`` for a close button that "
                "fires the optional ``on_close`` server "
                "handler. The Server playground card stress-tests "
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

                    ui.heading("Colors (auto-icon)", level=3)
                    with ui.vstack():
                        ui.alert("Info — auto icon.", color="info")
                        ui.alert("Success — auto icon.", color="success")
                        ui.alert("Warning — auto icon.", color="warning")
                        ui.alert("Error — auto icon.", color="error")

                    ui.heading("Colors (no auto-icon)", level=3)
                    ui.text(
                        "Primary / secondary / muted have no "
                        "automatic glyph — pass ``icon=`` if you "
                        "want one.",
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        ui.alert("Primary tinted.",   color="primary")
                        ui.alert("Secondary tinted.", color="secondary")
                        ui.alert("Muted tinted.",     color="muted")

                    ui.heading("With title", level=3)
                    with ui.vstack():
                        ui.alert("Your changes have been saved.",
                                 color="success", title="Saved")
                        ui.alert("We couldn't reach the API.",
                                 color="error", title="Connection failed")

                    ui.heading("Custom icon override", level=3)
                    with ui.vstack():
                        ui.alert("Custom icon overrides the auto-pick.",
                                 color="info", icon="bell")
                        ui.alert("Any Iconify name works.",
                                 color="primary", icon="lightbulb")

                    ui.heading("Dismissible", level=3)
                    with ui.vstack():
                        ui.alert("Click × on the right to dismiss.",
                                 color="info", dismissible=True)
                        ui.alert("Dismissible with a title.",
                                 color="warning", title="Note",
                                 dismissible=True)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Two reactive text slots (``title`` / "
                        "``message``) plus an icon slot. message "
                        "(positional) accepts str, ClientBinding, "
                        "or a Component for rich content.",
                        color="muted", size="sm",
                    )

                    ui.heading("message=str (default)", level=3)
                    ui.alert("Plain string message.", color="info")

                    ui.heading("message=Component (rich content)",
                               level=3)
                    # Real clickable link as the message body —
                    # demonstrates that the Component slot accepts
                    # any composable child (link, formatted prose,
                    # icon group, …) and that interactivity inside
                    # the alert works end-to-end (href navigates,
                    # focus ring is keyboard-visible).
                    ui.alert(
                        ui.link("Click to retry",
                                href="#",
                                color="primary"),
                        color="error", title="Failed",
                    )

                    ui.heading("icon=Component (full Icon override)",
                               level=3)
                    ui.alert(
                        "Custom icon Component (not just a name).",
                        color="primary",
                        icon=ui.icon("rocket", color="warning"),
                    )

                    ui.heading("icon=False (opt out of auto-icon)",
                               level=3)
                    ui.text(
                        "When the color triggers an auto-icon (info / "
                        "success / warning / error) but you want a "
                        "clean banner without the chrome — pass "
                        "``icon=False`` to suppress it entirely.",
                        color="muted", size="xs",
                    )
                    ui.alert(
                        "Clean info banner — no leading icon.",
                        color="info", icon=False,
                    )

                    ui.text(
                        "title / message = ClientBinding — see "
                        "Client playground",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty message", level=3)
                    ui.alert("", color="info")

                    ui.heading("Very long message (300 chars)", level=3)
                    ui.alert(
                        "Lorem ipsum dolor sit amet, consectetur "
                        "adipiscing elit. " * 4,
                        color="info",
                    )

                    ui.heading("Emoji + multi-script", level=3)
                    ui.alert("Ship 🚀 — שלום — 中文 — مرحبا",
                             color="success")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the message — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    ui.alert("<script>alert(1)</script>", color="error")

                    ui.heading("Title only, no message", level=3)
                    ui.alert("", color="warning", title="Just a heading")

                    ui.heading("Invalid icon name (silent fallback)",
                               level=3)
                    ui.alert("Invalid icon — no glyph but layout "
                             "stays.",
                             color="info",
                             icon="this-icon-does-not-exist")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Alert nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Stack of mixed alerts (changelog)",
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.alert("Release 2.0.4 is live.",
                                 color="success", title="Deployed")
                        ui.alert("Background migration is at 78%.",
                                 color="info", title="Migration")
                        ui.alert("Cache hit ratio degraded by 12%.",
                                 color="warning", title="Heads-up")

                    ui.heading("Inside ui.card (settings panel)",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Notifications", level=3)
                            ui.alert(
                                "Email notifications are paused while "
                                "your domain is being verified.",
                                color="warning", dismissible=True,
                            )
                            with ui.hstack(justify="end"):
                                ui.button("Resume", color="primary")

                    ui.heading("Inside ui.dialog (modal feedback)",
                               level=3)
                    ui.text(
                        "Dialog stays closed in this static demo — "
                        "the structural composition still type-checks.",
                        color="muted", size="xs",
                    )
                    ui.alert(
                        "Your trial expires in 3 days.",
                        color="warning", title="Trial",
                        dismissible=True,
                    )

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Alert does NOT auto-set ``role=\"alert\"`` "
                        "because the ARIA role carries strong "
                        "interrupt-now semantics — wrong for a "
                        "routine info panel. Callers that need it "
                        "pass ``attrs={\"role\": \"alert\"}`` "
                        "explicitly (or the ``role=alert`` line in "
                        "the Server playground's extra_attrs).",
                        color="muted", size="sm",
                    )
                    ui.alert(
                        "Important — opt-in role=alert.",
                        color="error", title="Connection lost",
                        dismissible=True,
                        attrs={"role": "alert"},
                    )

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
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Alert's ``BINDABLE_PROPS = "
                        "('title', 'message')`` contract. Title + "
                        "message swap via ``bz-text``. Color and "
                        "dismissible are design-time.",
                        color="muted", size="sm",
                    )
                    client = AlertClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("title"):
                            ui.input(value=client.title,
                                     placeholder="Live title")
                        with control("message"):
                            ui.textarea(value=client.message, rows=3)

                    ui.divider()

                    with ui.flex(justify="center", align="stretch",
                                 classes="min-h-16"):
                        ui.alert(client.message,
                                 title=client.title,
                                 dismissible=True,
                                 color="info")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-text on title + message "
                        "spans, bz-data + bz-show on the root, "
                        "bz-on:click on the dismiss button.",
                        serialize_html(
                            ui.alert(client.message,
                                     title=client.title,
                                     dismissible=True,
                                     color="info")
                        ),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Dismiss event wired to a client "
                        "expression that pushes onto a ClientState "
                        "list — zero network. Dismiss the alert "
                        "below and watch the log update without a "
                        "refresh.",
                        color="muted", size="sm",
                    )
                    cevents = AlertClientEvents()
                    ui.alert(
                        "Dismiss me — the runtime pushes 'close' onto "
                        "the log.",
                        color="info", dismissible=True,
                        on_close=cevents.log.push("close"),
                    )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.AlertClientEvents.default.log || '
                        '[]).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — @close listener on the "
                        "root ; the client expression pushes the "
                        "event name onto the bound list.",
                        serialize_html(
                            ui.alert(
                                "Dismiss me",
                                color="info", dismissible=True,
                                on_close=cevents.log.push("close"),
                            )
                        ),
                    )
