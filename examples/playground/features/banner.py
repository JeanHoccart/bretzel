"""``Banner`` test bench — full-width page-level status strip.

Eight visual cards : Reference / Banner vs Alert / Edge cases / A11y /
Server playground / Server events / Client playground / Client events.
``BINDABLE_PROPS = ("title", "message", "dismissible")`` ; one event
``close``.

**Banner vs Alert** : visually distinct on purpose.
- ``ui.alert(...)`` — inline, rounded, padded. Sits where you put
  it inside a card / form for context-local messages.
- ``ui.banner(...)`` — full-width edge-to-edge with a coloured left
  bar. Pushes against the parent's edges by default (no rounded
  corners) so it reads as page-level chrome rather than inline
  content. Convention used by Material / Atlassian / Tailwind UI.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/banner"

COLORS = ["info", "success", "warning", "error", "muted", "primary",
          "secondary"]
SIZES  = ["sm", "md", "lg"]


# ── State ─────────────────────────────────────────────────────────────


class BannerPlayground(PageState):
    message:     str  = field(default="Your trial expires in 3 days")
    title:       str  = field(default="")
    icon:        str  = field(default="")
    color:       str  = field(default="warning")
    size:        str  = field(default="md")
    dismissible: bool = field(default=True)
    has_action:  bool = field(default=True)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class BannerServerEvents(PageState):
    count: int = field(default=0)


class BannerClient(ClientState, persist="memory"):
    """Mirror of Banner's BINDABLE_PROPS subset that lends itself
    to typing (title / message). ``dismissible`` is also bindable
    but typically static."""

    title:   str = field(default="")
    message: str = field(default="Type below to update")


class BannerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ── Handlers ──────────────────────────────────────────────────────────


def server_changed(state: BannerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def log_close() -> None:
    state = BannerServerEvents()
    state.count += 1


def reset_dismiss() -> None:
    BannerServerEvents().count = 0


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


def build_preview(state: BannerPlayground) -> dict:
    kwargs: dict = {
        "color": state.color,
        "size": state.size,
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# ── Refreshables ──────────────────────────────────────────────────────


@refreshable(deps=[BannerPlayground])
def server_panel() -> None:
    state = BannerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("message"):
            ui.input(value=state.message, on_change=server_changed)
        with control("title (optional)"):
            ui.input(value=state.title,
                     placeholder="What's new",
                     on_change=server_changed)
        with control("icon (overrides auto-icon)"):
            ui.input(value=state.icon,
                     placeholder="rocket",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("dismissible"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("has_action"):
            ui.switch(checked=state.has_action,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-xl",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="trial-banner",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Trial expiry banner",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("extra_attrs (key=value per line)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=banner",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="System message",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    # LIVE preview — actually rendered in the page.
    kwargs = build_preview(state)
    live = ui.banner(state.message, **kwargs)
    if state.has_action:
        with live:
            ui.button("Take action", color="primary", size="sm")

    ui.divider()

    # Separate instance for serialize_html (which detaches its
    # argument from the parent context).
    snap = ui.banner(state.message, **kwargs)
    if state.has_action:
        with snap:
            ui.button("Take action", color="primary", size="sm")
    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(snap),
    )


@refreshable(deps=[BannerServerEvents])
def dismiss_demo() -> None:
    state = BannerServerEvents()
    ui.text(
        "``on_close`` server handler — fires AFTER the client-side "
        "close. Useful for marking a notification read / logging.",
        color="muted", size="sm",
    )
    ui.banner(
        "Click the × to dismiss",
        color="info",
        dismissible=True,
        on_close=log_close,
    )
    with ui.hstack(justify="between", align="center"):
        ui.text(f"Dismissed count : {state.count}",
                color="muted", size="sm",
                classes="font-mono")
        ui.button("Reset count", variant="ghost", size="sm",
                  on_click=reset_dismiss,
                  disabled=state.count == 0)


# ── Page ──────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Banner", level=1)
            ui.text(
                "Full-width edge-to-edge status strip — page-level "
                "announcement (trial expiring, maintenance, new "
                "feature). **Banner vs Alert** : Alert is inline + "
                "rounded + padded (context-local) ; Banner is "
                "full-width with a coloured left bar (page chrome). "
                "Non-rounded by default is intentional — that's the "
                "visual signal \"system message, not inline content\".",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading("Colors (auto-icon for semantics)",
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.banner("Info — neutral hint",
                                  color="info")
                        ui.banner("Success — saved!",
                                  color="success")
                        ui.banner(
                            "Warning — trial expires in 3 days",
                            color="warning")
                        ui.banner("Error — something went wrong",
                                  color="error")
                        ui.banner("Muted (no auto-icon)",
                                  color="muted")
                        ui.banner("Primary (no auto-icon)",
                                  color="primary")

                    ui.heading("With title + message", level=3)
                    ui.banner(
                        "Click the action to enable it on your "
                        "workspace.",
                        title="New dashboard available",
                        color="info",
                    )

                    ui.heading(
                        "Explicit icon override", level=3,
                    )
                    ui.banner(
                        "Custom icon — overrides the semantic auto-pick",
                        color="info",
                        icon="zap",
                    )

                    ui.heading("Sizes (sm / md / lg)", level=3)
                    with ui.vstack(gap="sm"):
                        for s in ui.each(SIZES):
                            ui.banner(f"size = {s}",
                                      color="info", size=s)

                    ui.heading("With action slot", level=3)
                    with ui.banner(
                        "New version 2.0 is ready to install",
                        title="Update available",
                        color="info",
                    ):
                        ui.button("Install now", color="primary",
                                  size="sm")
                        ui.button("Later", variant="ghost", size="sm")

                    ui.heading("Dismissible", level=3)
                    ui.banner(
                        "Click the × to close — purely client-side, "
                        "persists until reload.",
                        color="muted",
                        dismissible=True,
                    )

            # ── Card 2 — Banner vs Alert ────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Banner vs Alert — pick the right one",
                               level=2)
                    ui.text(
                        "Both signal status. Pick based on intent :",
                        color="muted", size="sm",
                    )

                    ui.heading(
                        "Alert — inline, rounded, padded "
                        "(context-local)", level=3,
                    )
                    ui.text(
                        "Use inside a card / form / list row when "
                        "the message belongs to the content around "
                        "it. The rounded corners + padding signal "
                        "\"part of the same block as my neighbours\".",
                        color="muted", size="sm",
                    )
                    ui.alert(
                        "Saved successfully.",
                        color="success",
                    )

                    ui.heading(
                        "Banner — full-width, coloured left bar "
                        "(page chrome)", level=3,
                    )
                    ui.text(
                        "Use at the top of a page / section for a "
                        "system message that applies to the whole "
                        "view. The full-width + left bar + flat "
                        "corners signal \"chrome, not inline\".",
                        color="muted", size="sm",
                    )
                    ui.banner(
                        "Scheduled maintenance Sunday 02:00 UTC.",
                        color="warning",
                    )

                    ui.heading("Side-by-side", level=3)
                    ui.text(
                        "Same message, same color — different "
                        "visual weight :",
                        color="muted", size="sm",
                    )
                    ui.alert("This is an Alert.", color="info")
                    ui.banner("This is a Banner.", color="info")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Very long message (wraps)",
                               level=3)
                    ui.banner(
                        "A very long message that should wrap "
                        "gracefully inside the banner's content "
                        "column, without overflowing or pushing "
                        "the action slot off-screen. The content "
                        "column has ``min-w-0`` so the wrapping "
                        "works correctly even when the action row "
                        "is wide.",
                        color="info",
                    )

                    ui.heading("Title-only (no message)", level=3)
                    ui.banner("", title="Title without body",
                              color="info")

                    ui.heading(
                        "HTML special chars (XSS escape)", level=3,
                    )
                    ui.banner(
                        "<script>alert(1)</script>",
                        title="<em>Escaped</em> title",
                        color="error",
                    )

                    ui.heading("Rounded variant via classes=", level=3)
                    ui.banner(
                        "Add ``classes=\"rounded-xl mx-2\"`` to "
                        "round a Banner — useful when nesting "
                        "inside a Card.",
                        color="info",
                        classes="rounded-xl",
                    )

                    ui.heading("Nested inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Settings panel", weight="bold")
                            ui.banner(
                                "Changes are saved automatically.",
                                color="info", classes="rounded-lg",
                            )
                            ui.text("Rest of the panel content…",
                                    color="muted", size="sm")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "``role=\"status\"`` on the root — screen "
                        "readers announce the message. Dismiss "
                        "button is a real ``<button>`` with "
                        "``aria-label=\"Dismiss\"`` (keyboard-"
                        "actionable). The close is purely client-"
                        "side : a local ``bz-data`` ``open`` flag "
                        "the × button flips ; an optional server "
                        "``on_close`` handler fires via "
                        "``$dispatch('close')`` after.",
                        color="muted", size="sm",
                    )

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    server_panel()

            # ── Card 6 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events — on_close", level=2)
                    dismiss_demo()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "``title`` and ``message`` accept a "
                        "``ClientBinding`` — the copy follows live "
                        "state without a server round-trip.",
                        color="muted", size="sm",
                    )
                    cstate = BannerClient(key="live")
                    with ui.vstack(gap="sm"):
                        ui.input(value=cstate.title,
                                 placeholder="Live title…")
                        ui.input(value=cstate.message,
                                 placeholder="Live message…")
                    ui.banner(cstate.message,
                              title=cstate.title,
                              color="info")

            # ── Card 8 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``on_close`` wired to a client expression "
                        "that pushes onto a ClientState list. Zero "
                        "network ; the log below re-renders via "
                        "bz-text on every push.",
                        color="muted", size="sm",
                    )
                    cevents = BannerClientEvents()
                    ui.banner(
                        "Dismiss me to fire the client event.",
                        title="Client-event banner",
                        color="warning",
                        dismissible=True,
                        on_close=cevents.log.push("close"),
                    )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.BannerClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    representative = ui.banner(
                        "Sample",
                        title="Client-event banner",
                        color="warning",
                        dismissible=True,
                        on_close=cevents.log.push("close"),
                    )
                    emitted_html_block(
                        "Emitted HTML — client expression pushes the "
                        "event name onto the bound list, zero "
                        "round-trip.",
                        serialize_html(representative),
                    )
