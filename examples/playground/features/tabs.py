"""``Tabs`` (+ ``Tab``, ``TabPanel``) test bench.

Nine visual cards : full gabarit. ``Tabs.BINDABLE_PROPS = ("value",)``
— the active tab id is bindable ; size / color stay design-time
(single style, no variant / orientation). ``Tabs`` event : ``change``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/tabs"


SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]


class TabsPlayground(PageState):
    value:       str  = field(default="a")
    name:        str  = field(default="")
    size:        str  = field(default="md")
    color:       str  = field(default="primary")
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


class TabsEvents(PageState):
    log: list = field(default_factory=list)


class TabsClient(ClientState, persist="memory"):
    value: str = field(default="a")


class TabsClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# Drives the server-events demo Tabs. ``value=tab_state.value`` →
# autoname derives ``name="value"`` from the binding's field_name →
# the handler ``log_change(value=...)`` receives it. No manual
# ``name="value"`` on the Tabs anywhere — that's the CLAUDE.md rule.
class TabsServerEvents(ClientState, persist="memory"):
    value: str = field(default="a")


def log(name: str) -> None:
    state = TabsEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    log(f"change(value={value!r})")


def clear_log() -> None:
    state = TabsEvents()
    state.log = []


def server_changed(state: TabsPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value={value!r})")


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


def build_preview(state: TabsPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "size": state.size,
        "color": state.color,
    }
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[TabsPlayground])
def server_panel() -> None:
    state = TabsPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (active tab)"):
            ui.select(value=state.value,
                      options=[("a", "A"), ("b", "B"), ("c", "C")],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="active",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-6",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-tabs",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Page sections",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 480px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=tabs",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Switch panels",
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

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        with ui.tabs(**kwargs):
            ui.tab("a", label="Alpha")
            ui.tab("b", label="Beta")
            ui.tab("c", label="Gamma")
            with ui.tab_panel(tab="a"):
                ui.text("Alpha panel content.")
            with ui.tab_panel(tab="b"):
                ui.text("Beta panel content.")
            with ui.tab_panel(tab="c"):
                ui.text("Gamma panel content.")

    ui.divider()

    preview = ui.tabs(**kwargs)
    with preview:
        ui.tab("a", label="A")
        ui.tab("b", label="B")
        with ui.tab_panel(tab="a"):
            ui.text("A")
        with ui.tab_panel(tab="b"):
            ui.text("B")
    emitted_html_block(
        "Emitted HTML (Tabs + Tab + TabPanel)",
        serialize_html(preview),
    )


@refreshable(deps=[TabsEvents])
def events_panel() -> None:
    state = TabsEvents()

    ui.text(
        "Tabs fires a single ``change`` event when the user picks "
        "a different tab — the new tab id is the kwarg.",
        color="muted", size="sm",
    )

    # ``value=tab_state.value`` (binding) → AUTONAME_FROM="value"
    # derives ``name="value"`` from the binding's field_name → the
    # hidden input carries it → the dispatcher's payload matches
    # the handler's ``value=`` kwarg. NO manual ``name=`` (CLAUDE.md
    # règle 4 : autoname est le canonical path, ``name=`` resté en
    # escape hatch).
    tab_state = TabsServerEvents()
    with ui.tabs(value=tab_state.value, on_change=log_change):
        ui.tab("a", label="A")
        ui.tab("b", label="B")
        ui.tab("c", label="C")
        with ui.tab_panel(tab="a"):
            ui.text("A panel")
        with ui.tab_panel(tab="b"):
            ui.text("B panel")
        with ui.tab_panel(tab="c"):
            ui.text("C panel")

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
        ui.text("(no events yet — click a different tab above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.tabs(value=tab_state.value, on_change=log_change)
    with representative:
        ui.tab("a", label="A")
        ui.tab("b", label="B")
        with ui.tab_panel(tab="a"):
            ui.text("A")
    emitted_html_block(
        "Emitted HTML (Tabs with on_change handler)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Tabs", level=1)
            ui.text(
                "Switchable content panels. ``Tabs`` owns the "
                "active id (literal, server-resolved, or bound to "
                "ClientState) ; ``Tab`` declares each trigger ; "
                "``TabPanel`` holds the matching content. Panels "
                "swap client-side ``bz-show`` — zero network on "
                "switch.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic", level=3)
                    with ui.tabs(value="a"):
                        ui.tab("a", label="First")
                        ui.tab("b", label="Second")
                        ui.tab("c", label="Third")
                        with ui.tab_panel(tab="a"):
                            ui.text("Content of the first tab.")
                        with ui.tab_panel(tab="b"):
                            ui.text("Content of the second tab.")
                        with ui.tab_panel(tab="c"):
                            ui.text("Content of the third tab.")

                    ui.heading("Sizes", level=3)
                    for s in SIZES:
                        ui.text(f"size={s}",
                                color="muted", size="xs")
                        with ui.tabs(value="a", size=s):
                            ui.tab("a", label="One")
                            ui.tab("b", label="Two")
                            with ui.tab_panel(tab="a"):
                                ui.text("One panel.")
                            with ui.tab_panel(tab="b"):
                                ui.text("Two panel.")

                    ui.heading("Colors", level=3)
                    for c in COLORS:
                        with ui.tabs(value="a", color=c):
                            ui.tab("a", label=f"{c.title()} A")
                            ui.tab("b", label=f"{c.title()} B")
                            with ui.tab_panel(tab="a"):
                                ui.text(f"{c} panel A.")
                            with ui.tab_panel(tab="b"):
                                ui.text(f"{c} panel B.")

                    ui.heading("Disabled tab", level=3)
                    with ui.tabs(value="a"):
                        ui.tab("a", label="Available")
                        ui.tab("b", label="Available")
                        ui.tab("c", label="Coming soon",
                               disabled=True)
                        with ui.tab_panel(tab="a"):
                            ui.text("A panel")
                        with ui.tab_panel(tab="b"):
                            ui.text("B panel")
                        with ui.tab_panel(tab="c"):
                            ui.text("C panel (unreachable)")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Tab leaves declare ``label`` (str) + "
                        "optional ``icon``. TabPanel is a container "
                        "— children inside the ``with`` block are "
                        "the panel content.",
                        color="muted", size="sm",
                    )

                    ui.heading("Tab with icon", level=3)
                    with ui.tabs(value="home"):
                        ui.tab("home",     label="Home",
                               icon="home")
                        ui.tab("profile",  label="Profile",
                               icon="user")
                        ui.tab("settings", label="Settings",
                               icon="settings")
                        with ui.tab_panel(tab="home"):
                            ui.text("Home panel content.")
                        with ui.tab_panel(tab="profile"):
                            ui.text("Profile panel content.")
                        with ui.tab_panel(tab="settings"):
                            ui.text("Settings panel content.")

                    ui.heading("TabPanel = rich layout", level=3)
                    with ui.tabs(value="overview"):
                        ui.tab("overview", label="Overview")
                        ui.tab("activity", label="Activity")
                        with ui.tab_panel(tab="overview"):
                            with ui.vstack():
                                ui.heading("Project Aurora",
                                           level=3)
                                ui.text("Multi-line body, with a "
                                        "button below.",
                                        color="muted")
                                ui.button("Edit",
                                          icon_left="pencil",
                                          variant="outline")
                        with ui.tab_panel(tab="activity"):
                            with ui.vstack(gap="sm"):
                                ui.text("Activity row 1",
                                        color="muted")
                                ui.text("Activity row 2",
                                        color="muted")
                                ui.text("Activity row 3",
                                        color="muted")

                    ui.text(
                        "``value`` accepts ClientBinding — see Card 8 "
                        "(Client playground) below for the live "
                        "binding demo.",
                        color="muted", size="sm",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Single tab", level=3)
                    with ui.tabs(value="only"):
                        ui.tab("only", label="The only one")
                        with ui.tab_panel(tab="only"):
                            ui.text("Lone panel — but tabs still "
                                    "render the rail.")

                    ui.heading("Many tabs (overflow scroll)", level=3)
                    with ui.tabs(value="t1"):
                        for i in range(1, 16):
                            ui.tab(f"t{i}", label=f"Tab {i}")
                        for i in range(1, 16):
                            with ui.tab_panel(tab=f"t{i}"):
                                ui.text(f"Panel {i}")

                    ui.heading("Very long labels", level=3)
                    with ui.tabs(value="a"):
                        ui.tab("a",
                               label="A long tab label that may wrap")
                        ui.tab("b", label="Another long-ish label")
                        with ui.tab_panel(tab="a"):
                            ui.text("A panel.")
                        with ui.tab_panel(tab="b"):
                            ui.text("B panel.")

                    ui.heading("value pointing to non-existent tab",
                               level=3)
                    ui.text(
                        "If ``value=`` doesn't match any tab id, "
                        "no panel shows — the rail still renders.",
                        color="muted", size="xs",
                    )
                    with ui.tabs(value="ghost"):
                        ui.tab("a", label="A")
                        ui.tab("b", label="B")
                        with ui.tab_panel(tab="a"):
                            ui.text("A panel")
                        with ui.tab_panel(tab="b"):
                            ui.text("B panel")

                    ui.heading("HTML-special label (XSS escape)",
                               level=3)
                    with ui.tabs(value="a"):
                        ui.tab("a",
                               label="<script>alert(1)</script>")
                        ui.tab("b", label="Safe")
                        with ui.tab_panel(tab="a"):
                            ui.text("A")
                        with ui.tab_panel(tab="b"):
                            ui.text("B")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Tabs in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Settings page (inside Card)", level=3)
                    with ui.card():
                        with ui.tabs(value="general"):
                            ui.tab("general",  label="General",
                                   icon="settings")
                            ui.tab("billing",  label="Billing",
                                   icon="credit-card")
                            ui.tab("security", label="Security",
                                   icon="shield")
                            with ui.tab_panel(tab="general"):
                                with ui.form_field(
                                    label="Display name",
                                    hint="What other users see"):
                                    ui.input(placeholder="Ada")
                            with ui.tab_panel(tab="billing"):
                                ui.text("Billing information.",
                                        color="muted")
                            with ui.tab_panel(tab="security"):
                                with ui.vstack():
                                    ui.switch(label="2FA enabled",
                                              checked=True)
                                    ui.switch(label="Email alerts",
                                              checked=True)

                    ui.heading("Inside ui.dialog", level=3)
                    with ui.dialog(
                        title="Account settings",
                        width="lg",
                    ) as settings_dlg:
                        with ui.tabs(value="profile"):
                            ui.tab("profile",
                                   label="Profile")
                            ui.tab("notifications",
                                   label="Notifications")
                            with ui.tab_panel(tab="profile"):
                                ui.text("Profile fields.",
                                        color="muted")
                            with ui.tab_panel(tab="notifications"):
                                ui.text("Notification toggles.",
                                        color="muted")
                    ui.button("Open settings dialog",
                              on_click=settings_dlg.open())

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Tab rail emits ``role=\"tablist\"``, each "
                        "Tab carries ``role=\"tab\"`` + reactive "
                        "``aria-selected`` (the active tab) + roving "
                        "``tabindex`` (0 on the active tab, -1 on the "
                        "rest) ; each TabPanel carries "
                        "``role=\"tabpanel\"`` and toggles via "
                        "``bz-show``. The active tab is picked by "
                        "click (Tab/Shift+Tab reach the active one "
                        "via the roving tabindex).",
                        color="muted", size="sm",
                    )
                    with ui.tabs(value="a",
                                 aria_label="Demo tabs"):
                        ui.tab("a", label="Alpha",   icon="check")
                        ui.tab("b", label="Beta",    icon="check")
                        ui.tab("c", label="Gamma",   icon="check")
                        with ui.tab_panel(tab="a"):
                            ui.text("Alpha — Tab here, arrow keys "
                                    "to move.")
                        with ui.tab_panel(tab="b"):
                            ui.text("Beta panel.")
                        with ui.tab_panel(tab="c"):
                            ui.text("Gamma panel.")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every Tabs prop AND every escape hatch is "
                        "wired to a control ; the preview AND the "
                        "emitted HTML both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 7b — L'onglet dans l'URL ───────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("url= — l'onglet a une adresse", level=2)
                    ui.text(
                        "Clique un onglet et regarde la barre d'adresse : "
                        "elle devient ?onglet=… . Les flèches du navigateur "
                        "font ensuite l'aller-retour, et le lien est "
                        "partageable — c'est le même écran qui s'ouvre chez "
                        "qui le reçoit.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Opt-in : sans url=, un onglet ne publie rien. Ce "
                        "qui est dans l'URL part aussi dans l'historique, "
                        "les logs et le Referer.",
                        color="muted", size="sm",
                    )
                    with ui.flex(justify="center"):
                        with ui.tabs(value="apercu", url="onglet"):
                            ui.tab("apercu", label="Aperçu", icon="eye")
                            ui.tab("details", label="Détails", icon="list")
                            ui.tab("brut", label="Brut", icon="code")
                            with ui.tab_panel(tab="apercu"):
                                ui.text("?onglet est absent — c'est le défaut.")
                            with ui.tab_panel(tab="details"):
                                ui.text("?onglet=details")
                            with ui.tab_panel(tab="brut"):
                                ui.text("?onglet=brut")

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Tabs' ``BINDABLE_PROPS = "
                        "('value',)`` contract. The active id is "
                        "bound to a ClientState ; external "
                        "controls drive the tabs.",
                        color="muted", size="sm",
                    )
                    client = TabsClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (bound)"):
                            ui.select(value=client.value,
                                      options=[("a", "A"),
                                               ("b", "B"),
                                               ("c", "C")])

                    ui.divider()

                    with ui.flex(justify="center"):
                        with ui.tabs(value=client.value,
                                     color="primary"):
                            ui.tab("a", label="A")
                            ui.tab("b", label="B")
                            ui.tab("c", label="C")
                            with ui.tab_panel(tab="a"):
                                ui.text("Bound A panel")
                            with ui.tab_panel(tab="b"):
                                ui.text("Bound B panel")
                            with ui.tab_panel(tab="c"):
                                ui.text("Bound C panel")

                    ui.divider()

                    preview = ui.tabs(value=client.value)
                    with preview:
                        ui.tab("a", label="A")
                        ui.tab("b", label="B")
                        with ui.tab_panel(tab="a"):
                            ui.text("A")
                        with ui.tab_panel(tab="b"):
                            ui.text("B")
                    emitted_html_block(
                        "Emitted HTML — bz-show reads the bound "
                        "active id ; panels toggle without a "
                        "round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("change event wired to a client "
                            "expression that pushes the new tab id "
                            "onto a ClientState list. Zero network.",
                            color="muted", size="sm")
                    cevents = TabsClientEvents()
                    _new_value = ClientExpression("$event.target.value")
                    with ui.tabs(value="a",
                                 on_change=cevents.log.push(_new_value)):
                        ui.tab("a", label="A")
                        ui.tab("b", label="B")
                        ui.tab("c", label="C")
                        with ui.tab_panel(tab="a"):
                            ui.text("A")
                        with ui.tab_panel(tab="b"):
                            ui.text("B")
                        with ui.tab_panel(tab="c"):
                            ui.text("C")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.TabsClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.tabs(
                        value="a",
                        on_change=cevents.log.push(_new_value),
                    )
                    with preview:
                        ui.tab("a", label="A")
                        ui.tab("b", label="B")
                        with ui.tab_panel(tab="a"):
                            ui.text("A")
                        with ui.tab_panel(tab="b"):
                            ui.text("B")
                    emitted_html_block(
                        "Emitted HTML — the ``bz-on:change`` handler is "
                        "relocated onto the hidden input ; setTab only "
                        "flips the active value, and the hidden input's "
                        "``bz-effect`` re-fires ``change`` on every move "
                        "— the client expression pushes onto the bound "
                        "ClientState list.",
                        serialize_html(preview),
                    )
