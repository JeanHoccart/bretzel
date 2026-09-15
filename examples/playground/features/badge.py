"""``Badge`` test bench.

Eight visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Server events / Client playground.
``BINDABLE_PROPS = ("label", "dismissible")`` ; one event ``close``.

Six props : ``label`` (positional, str | ClientBinding | None),
``variant`` (soft / solid / outline), ``size``, ``color``,
``icon_left`` / ``icon_right`` (str | Component | ClientBinding),
``dismissible`` (bool — shows the × button + wires a local
client-side close flag).
"""

from functools import partial

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import (
    ClientExpression,
    ClientState,
    PageState,
    field,
)

from examples.playground.features.inspection import emitted_html_block


PATH = "/badge"


VARIANTS = ["soft", "solid", "outline"]
SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]


class BadgePlayground(PageState):
    label:       str  = field(default="New")
    variant:     str  = field(default="soft")
    size:        str  = field(default="sm")
    color:       str  = field(default="primary")
    icon_left:   str  = field(default="")
    icon_right:  str  = field(default="")
    dismissible: bool = field(default=False)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class BadgeClient(ClientState, persist="memory"):
    """Mirror of Badge's BINDABLE_PROPS = ('label',)."""

    label:       str  = field(default="3 unread")


class BadgeEvents(PageState):
    """Server-side log of close events fired by Badges in the
    Server events card."""

    log: list = field(default_factory=list)


class BadgeClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def server_changed(state: BadgePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[BadgePlayground] re-renders server_panel automatically.
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


def log_close(label: str = "") -> None:
    """Server-side ``on_close`` handler for the Server events card.
    The label is pushed as FormData ``value=`` via autoname when the
    badge's ``value=`` is bound to a ClientState field. Here we use
    ``partial(log_close, label)`` per badge so the right name lands."""
    state = BadgeEvents()
    state.log = [*state.log, label or "(no label)"]


def clear_events_log() -> None:
    BadgeEvents().log = []


def build_preview(state: BadgePlayground):
    kwargs: dict = {
        "variant": state.variant,
        "size": state.size,
        "color": state.color,
        "dismissible": state.dismissible,
    }
    if state.icon_left:
        kwargs["icon_left"] = state.icon_left
    if state.icon_right:
        kwargs["icon_right"] = state.icon_right
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
    return ui.badge(state.label, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[BadgeEvents])
def events_panel() -> None:
    """Server-side close event log. Each Badge wires
    ``on_close=partial(log_close, label)`` so the server handler
    knows which badge fired without relying on FormData (badges
    have no name/value to ship)."""
    state = BadgeEvents()

    ui.text(
        "Each Badge below has ``dismissible=True`` AND "
        "``on_close=partial(log_close, label)``. Click the × on "
        "any of them : the badge disappears client-side (the runtime "
        "``open`` flag), then ``$dispatch('close')`` fires the "
        "server handler which appends to this log.",
        color="muted", size="sm",
    )

    with ui.hstack(wrap=True):
        for label, c in [
            ("React",      "primary"),
            ("TypeScript", "info"),
            ("Frontend",   "success"),
            ("Beta",       "warning"),
            ("Deprecated", "error"),
        ]:
            ui.badge(
                label,
                color=c,
                dismissible=True,
                on_close=partial(log_close, label),
            )

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (server-side, newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_events_log,
                  disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. close({evt!r})",
                        color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet — click a × above)",
                color="muted", size="sm")


@refreshable(deps=[BadgePlayground])
def server_panel() -> None:
    state = BadgePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("label"):
            ui.input(value=state.label, placeholder="New",
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
        with control("icon_left"):
            ui.input(value=state.icon_left,
                     placeholder="ex: check / star",
                     on_change=server_changed)
        with control("icon_right"):
            ui.input(value=state.icon_right,
                     placeholder="ex: arrow-right",
                     on_change=server_changed)
        with control(
            "dismissible (× button — suppresses icon_right)"
        ):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-full",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-badge",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="3 unread items",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="letter-spacing: 0.05em",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=badge",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Recently updated",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Badge", level=1)
            ui.text(
                "Inline pill for counts / status / tags. Three "
                "variants (soft / solid / outline), every theme "
                "colour, optional icon slots. The Server playground "
                "card stress-tests every prop ; the emitted HTML is "
                "shown live underneath.",
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
                            ui.badge(v.title(), variant=v)

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="center"):
                        for s in SIZES:
                            ui.badge(s, size=s)

                    ui.heading("Colors (soft)", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.badge(c.title(), color=c)

                    ui.heading("Colors (solid)", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.badge(c.title(), color=c, variant="solid")

                    ui.heading("Colors (outline)", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.badge(c.title(), color=c, variant="outline")

                    ui.heading("Icon left", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("Verified", color="success",
                                 icon_left="check")
                        ui.badge("Premium",  color="warning",
                                 icon_left="star")
                        ui.badge("Beta",     color="info",
                                 icon_left="flask-conical")

                    ui.heading("Icon right", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("Trending", color="info",
                                 icon_right="trending-up")
                        ui.badge("3 new",    color="primary",
                                 icon_right="bell")
                        ui.badge("External", color="muted",
                                 icon_right="external-link")

                    ui.heading("Icon both sides", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("In flight", color="warning",
                                 icon_left="plane", icon_right="ellipsis")
                        ui.badge("Approved",  color="success",
                                 icon_left="check",
                                 icon_right="arrow-right")

                    ui.heading(
                        "Dismissible — × button + auto-hide", level=3,
                    )
                    ui.text(
                        "Pass ``dismissible=True`` to opt-in to the "
                        "client-side dismiss flow : the framework "
                        "appends an ``aria-label=\"Remove\"`` button "
                        "on the right, wires a local ``bz-data="
                        "\"{open: true}\"`` flag on the root, and the "
                        "click flips ``open`` to ``false`` — the "
                        "badge disappears via ``bz-show=\"open\"`` "
                        "without a server round-trip. Try clicking "
                        "the × on any of these :",
                        color="muted", size="sm",
                    )
                    with ui.hstack(wrap=True):
                        for label, c in [
                            ("React", "primary"),
                            ("TypeScript", "info"),
                            ("Frontend", "success"),
                            ("Beta", "warning"),
                            ("Deprecated", "error"),
                        ]:
                            ui.badge(
                                label,
                                color=c,
                                dismissible=True,
                            )

                    ui.heading(
                        "dismissible suppresses icon_right", level=3,
                    )
                    ui.text(
                        "When the × button shows up, it takes the "
                        "right edge of the pill — the ``icon_right`` "
                        "slot is silently dropped so the user has a "
                        "single, unambiguous click target. Compare :",
                        color="muted", size="sm",
                    )
                    with ui.hstack(wrap=True, align="center", gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("icon_right alone",
                                    color="muted", size="xs")
                            ui.badge("External",
                                     icon_right="external-link",
                                     color="info")
                        with ui.vstack(gap="xs"):
                            ui.text(
                                "dismissible (icon_right dropped)",
                                color="muted", size="xs",
                            )
                            ui.badge(
                                "External",
                                icon_right="external-link",
                                color="info",
                                dismissible=True,
                            )
                        with ui.vstack(gap="xs"):
                            ui.text("dismissible alone",
                                    color="muted", size="xs")
                            ui.badge("Alone", color="info",
                                     dismissible=True)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Three slots : ``label`` (positional), "
                        "``icon_left=`` (str shortcut or Component), "
                        "``icon_right=`` (same).",
                        color="muted", size="sm",
                    )

                    ui.heading("Default slot (label)", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("Plain")
                        ui.badge(ui.text("Custom span", color="success",
                                         weight="bold"))

                    ui.heading("icon_left slot — str shortcut", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("Verified", icon_left="check",
                                 color="success")

                    ui.heading("icon_left slot — Component override",
                               level=3)
                    with ui.hstack(wrap=True):
                        ui.badge(
                            "Crown holder",
                            icon_left=ui.icon("crown", color="warning"),
                            color="warning",
                        )

                    ui.heading("icon_right slot — Component override",
                               level=3)
                    with ui.hstack(wrap=True):
                        ui.badge(
                            "Outbound",
                            icon_right=ui.icon("external-link",
                                               color="info"),
                            color="info",
                        )

                    ui.text(
                        "label=ClientBinding — see Client playground",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Bind to a ClientState string ; the runtime swaps "
                        "the inner ``bz-text`` on every mutation. No "
                        "round-trip.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that historically break pills.",
                            color="muted", size="sm")

                    ui.heading("Empty label", level=3)
                    with ui.hstack():
                        ui.badge("")
                        ui.badge("", icon_left="check", color="success")

                    ui.heading("Very long label (60 chars)", level=3)
                    with ui.hstack():
                        ui.badge("A" * 60, color="primary")

                    ui.heading("Emoji + multi-script", level=3)
                    with ui.hstack(wrap=True):
                        ui.badge("Ship 🚀 — שלום — 中文")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        ui.badge("<script>alert(1)</script>")

                    ui.heading("Invalid icon name (no glyph, no crash)",
                               level=3)
                    with ui.hstack():
                        ui.badge("Broken",
                                 icon_left="this-icon-does-not-exist",
                                 color="error")

                    ui.heading("Pure count (no extra padding)", level=3)
                    with ui.hstack():
                        ui.badge("1",  color="error", variant="solid")
                        ui.badge("12", color="error", variant="solid")
                        ui.badge("99+",color="error", variant="solid")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Badge nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Next to ui.button (notification count)",
                               level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.button("Inbox", variant="outline",
                                  icon_left="inbox")
                        ui.badge("3", color="error", variant="solid")

                    ui.heading("Inside ui.card (header tag)", level=3)
                    with ui.card():
                        with ui.vstack():
                            with ui.hstack(align="center", gap="sm"):
                                ui.heading("Roadmap", level=3)
                                ui.badge("Q3 2026", color="primary")
                            ui.text("Card body copy.", color="muted")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.hstack():
                        with ui.tooltip("3 items pending review"):
                            ui.badge("3 pending", color="warning",
                                     icon_left="clock")

                    ui.heading("Inside ui.hstack with avatar", level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.avatar(initials="JD", color="primary")
                        ui.text("Jane Doe", weight="bold")
                        ui.badge("Admin", color="info")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Badges render as a styled ``<span>``. When "
                        "they carry meaning beyond pure decoration "
                        "(unread count, status, tag), pair them with "
                        "an ``aria-label`` that spells out the value "
                        "in words.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="lg"):
                        ui.badge("3", color="error", variant="solid",
                                 aria_label="3 unread messages")
                        ui.badge("New", color="primary",
                                 aria_label="New release available")
                        ui.badge("Active", color="success",
                                 icon_left="check",
                                 aria_label="Account is active")

                    ui.heading("Keyboard test (dismissible)", level=3)
                    ui.text(
                        "Tab onto the × button, press Space or Enter "
                        "to fire on_close.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        ui.badge("Tab here", color="primary",
                                 on_close=log_close)

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

            # ── Card 7 — Server events (close) ──────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events — on_close", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Badge's ``BINDABLE_PROPS = "
                        "('label',)`` contract. the runtime "
                        "swaps the inner ``bz-text`` on every label "
                        "mutation — no network round-trip. "
                        "``dismissible`` is design-time (adding the × "
                        "button restructures the pill, so it can't "
                        "flip client-side).",
                        color="muted", size="sm",
                    )
                    client = BadgeClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("label"):
                            ui.input(value=client.label,
                                     placeholder="3 unread")

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.badge(client.label, color="primary",
                                 icon_left="bell")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;span bz-text&gt; inside "
                        "the badge pill, bound to "
                        "$bz.state.BadgeClient.default.label.",
                        serialize_html(
                            ui.badge(client.label, color="primary",
                                     icon_left="bell")
                        ),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``on_close`` accepts an Client string : "
                        "click the × and the handler pushes onto a "
                        "ClientState list, no round-trip. The log "
                        "below re-renders via ``bz-text`` on every "
                        "push.",
                        color="muted", size="sm",
                    )
                    cevents = BadgeClientEvents()
                    with ui.hstack(wrap=True):
                        for label in ("apple", "banana", "cherry"):
                            ui.badge(
                                label,
                                color="info",
                                dismissible=True,
                                on_close=cevents.log.push(label),
                            )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text(
                            "Live log (client-reactive — no refresh)",
                            color="muted", size="sm",
                        )
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.BadgeClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — one of the "
                        "dismissible badges). @close listener on "
                        "the root ; the client expression pushes "
                        "the badge label onto the bound list.",
                        serialize_html(
                            ui.badge(
                                "apple",
                                color="info",
                                dismissible=True,
                                on_close=cevents.log.push("apple"),
                            )
                        ),
                    )
