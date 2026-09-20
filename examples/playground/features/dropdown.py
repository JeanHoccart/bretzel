"""``Dropdown`` (+ ``DropdownItem``) test bench.

Ten visual cards : full gabarit. Dropdown ``BINDABLE_PROPS =
("open",)`` — the open flag gets a dedicated Client playground card ;
DropdownItem ``BINDABLE_PROPS = ("disabled",)``. Both have events —
Dropdown : ``open`` / ``close`` ; DropdownItem : ``click`` (via the
standard on_click flow).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/dropdown"


POSITIONS = ["top", "bottom", "left", "right"]
ALIGNS    = ["start", "center", "end"]


class DropdownPlayground(PageState):
    position:    str  = field(default="bottom")
    align:       str  = field(default="start")
    dismissible: bool = field(default=True)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class DropdownEvents(PageState):
    log: list = field(default_factory=list)


class DropdownClient(ClientState, persist="memory"):
    open: bool = field(default=False)


class DropdownClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = DropdownEvents()
    state.log = [*state.log, name]


def log_open()  -> None: log("open")
def log_close() -> None: log("close")
def log_edit()      -> None: log("Edit picked")
def log_duplicate() -> None: log("Duplicate picked")
def log_delete()    -> None: log("Delete picked")


def clear_log() -> None:
    state = DropdownEvents()
    state.log = []


def server_changed(state: DropdownPlayground) -> None:
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


def build_preview(state: DropdownPlayground) -> dict:
    kwargs: dict = {
        "position": state.position,
        "align": state.align,
        "dismissible": state.dismissible,
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[DropdownPlayground])
def server_panel() -> None:
    state = DropdownPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("position"):
            ui.select(value=state.position,
                      options=[(p, p) for p in POSITIONS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.align,
                      options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("dismissible"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!min-w-48",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-dropdown",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Actions menu",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="min-width: 240px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=dropdown",
                        on_change=server_changed)
        with control("tooltip (on trigger)"):
            ui.input(value=state.tooltip,
                     placeholder="Open menu",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center", classes="min-h-32"):
        with ui.dropdown(
            trigger=ui.button("Open preview menu",
                              color="primary",
                              icon_right="chevron-down"),
            **kwargs,
        ):
            ui.dropdown_item(label="Edit",      icon_left="pencil")
            ui.dropdown_item(label="Duplicate", icon_left="copy")
            ui.dropdown_item(label="Delete",    icon_left="trash-2",
                             color="error")

    ui.divider()

    preview = ui.dropdown(
        trigger=ui.button("Open preview menu", color="primary"),
        **kwargs,
    )
    with preview:
        ui.dropdown_item(label="Edit",   icon_left="pencil")
        ui.dropdown_item(label="Delete", icon_left="trash-2",
                         color="error")
    emitted_html_block(
        "Emitted HTML (Dropdown + items)",
        serialize_html(preview),
    )


@refreshable(deps=[DropdownEvents])
def events_panel() -> None:
    state = DropdownEvents()

    ui.text(
        "Dropdown fires ``on_open`` AND ``on_close`` — both to the "
        "server on the same dropdown (the close handler rides a hidden "
        "carrier) ; each DropdownItem fires ``on_click`` when picked. "
        "The dropdown auto-closes on pick — open, close and pick all "
        "log in sequence.",
        color="muted", size="sm",
    )

    with ui.flex(justify="center", classes="min-h-32"):
        with ui.dropdown(
            trigger=ui.button("Open + close + pick logger",
                              color="primary"),
            on_open=log_open,
            on_close=log_close,
        ):
            ui.dropdown_item(label="Edit",      icon_left="pencil",
                             on_click=log_edit)
            ui.dropdown_item(label="Duplicate", icon_left="copy",
                             on_click=log_duplicate)
            ui.dropdown_item(label="Delete",    icon_left="trash-2",
                             color="error",
                             on_click=log_delete)

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
        ui.text("(no events yet — open and pick an item)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.dropdown(
        trigger=ui.button("Open", color="primary"),
        on_open=log_open,
        on_close=log_close,
    )
    with representative:
        ui.dropdown_item(label="Edit", icon_left="pencil",
                         on_click=log_edit)
    emitted_html_block(
        "Emitted HTML (Dropdown + single item with handlers)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Dropdown", level=1)
            ui.text(
                "Anchored menu of clickable rows. Compose with "
                "``trigger=`` + ``ui.dropdown_item`` children inside "
                "the ``with`` block. Click-outside / Escape dismiss "
                "by default ; the dropdown auto-closes on pick. "
                "Three ways to drive the open state : ``trigger=`` "
                "built-in (simplest), ``as dd`` + ``dd.open()`` "
                "(imperative API — default for purely-visual menus), "
                "or ``open=ClientBinding`` (when another component "
                "needs to read or react to the state). The 3 modes "
                "are compared side-by-side in Card 9.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Click each trigger to see the menu.",
                            color="muted", size="sm")

                    ui.heading("Basic — trigger= built-in", level=3)
                    ui.text(
                        "Simplest path : pass a ``trigger=`` component "
                        "and the dropdown wires its ``bz-on:click`` for you. "
                        "Zero state, zero variable to capture.",
                        color="muted", size="sm",
                    )
                    with ui.dropdown(
                        trigger=ui.button("Actions",
                                          icon_right="chevron-down"),
                    ):
                        ui.dropdown_item(label="Edit",
                                         icon_left="pencil")
                        ui.dropdown_item(label="Duplicate",
                                         icon_left="copy")
                        ui.dropdown_item(label="Delete",
                                         icon_left="trash-2",
                                         color="error")

                    ui.heading(
                        "Basic — external trigger via .open()",
                        level=3,
                    )
                    ui.text(
                        "Same dropdown, opened from sibling buttons. "
                        "Capture the instance via ``as dd`` and call "
                        "``dd.open()`` / ``dd.close()`` — client-local "
                        "state, no ClientState declared. **Note** : a "
                        "dropdown's panel is ``position: absolute`` and "
                        "needs a visual anchor element, so we keep an "
                        "``Anchor`` trigger button alongside the external "
                        "controls — clicking it also opens (both paths "
                        "flip the same local flag).",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        with ui.dropdown(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                        ) as basic_dd:
                            ui.dropdown_item(label="Edit",
                                             icon_left="pencil")
                            ui.dropdown_item(label="Duplicate",
                                             icon_left="copy")
                            ui.dropdown_item(
                                label="Close from inside",
                                icon_left="x",
                                on_click=basic_dd.close(),
                            )
                        ui.button(
                            "Open via .open()",
                            on_click=basic_dd.open(),
                        )
                        ui.button(
                            "Toggle via .toggle()",
                            variant="outline",
                            on_click=basic_dd.toggle(),
                        )

                    ui.heading("Positions", level=3)
                    with ui.hstack(wrap=True, classes="min-h-32"):
                        for p in POSITIONS:
                            with ui.dropdown(
                                trigger=ui.button(p.title()),
                                position=p,
                            ):
                                ui.dropdown_item(label=f"{p} item 1")
                                ui.dropdown_item(label=f"{p} item 2")

                    ui.heading("Alignments", level=3)
                    with ui.hstack(wrap=True, classes="min-h-32"):
                        for a in ALIGNS:
                            with ui.dropdown(
                                trigger=ui.button(a.title()),
                                align=a,
                            ):
                                ui.dropdown_item(
                                    label=f"align={a} item 1")
                                ui.dropdown_item(
                                    label=f"align={a} item 2")

                    ui.heading("Persistent (dismissible=False)",
                               level=3)
                    with ui.dropdown(
                        trigger=ui.button("Persistent",
                                          color="error"),
                        dismissible=False,
                    ):
                        ui.dropdown_item(label="Only an explicit "
                                               "pick dismisses")
                        ui.dropdown_item(label="Item B")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Two slots : ``trigger`` (Component) and the "
                        "``with`` block holding the items. Items "
                        "accept ``label`` / ``icon_left`` / ``href`` "
                        "/ ``color`` / ``disabled`` / ``on_click``.",
                        color="muted", size="sm",
                    )

                    ui.heading("trigger = IconButton", level=3)
                    with ui.dropdown(
                        trigger=ui.icon_button("more-horizontal",
                                               variant="ghost",
                                               aria_label="Actions"),
                    ):
                        ui.dropdown_item(label="Rename",
                                         icon_left="pencil")
                        ui.dropdown_item(label="Archive",
                                         icon_left="archive")

                    ui.heading("Items as links (href=…)", level=3)
                    with ui.dropdown(
                        trigger=ui.button("Navigate"),
                    ):
                        ui.dropdown_item(label="Profile",
                                         icon_left="user",
                                         href="/")
                        ui.dropdown_item(label="Settings",
                                         icon_left="settings",
                                         href="/")
                        ui.dropdown_item(label="Docs",
                                         icon_left="book-open",
                                         href="/")

                    ui.heading("Disabled item", level=3)
                    with ui.dropdown(
                        trigger=ui.button("With locked"),
                    ):
                        ui.dropdown_item(label="Available")
                        ui.dropdown_item(label="Locked",
                                         disabled=True)
                        ui.dropdown_item(label="Available")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty dropdown (no items)", level=3)
                    with ui.dropdown(
                        trigger=ui.button("Empty"),
                    ):
                        pass

                    ui.heading("Many items (20+)", level=3)
                    with ui.dropdown(
                        trigger=ui.button("Long list"),
                    ):
                        for i in range(1, 21):
                            ui.dropdown_item(label=f"Item {i}")

                    ui.heading("Very long label", level=3)
                    with ui.dropdown(
                        trigger=ui.button("Long labels"),
                    ):
                        ui.dropdown_item(
                            label="A very long item label that may "
                                  "wrap or truncate in the menu",
                        )
                        ui.dropdown_item(label="Short")

                    ui.heading("HTML-special label (XSS escape)",
                               level=3)
                    with ui.dropdown(
                        trigger=ui.button("XSS labels"),
                    ):
                        ui.dropdown_item(
                            label="<script>alert(1)</script>",
                        )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common dropdown patterns.",
                            color="muted", size="sm")

                    ui.heading("Row actions menu (table cell)",
                               level=3)
                    with ui.card():
                        with ui.hstack(justify="between",
                                       align="center"):
                            with ui.hstack(align="center", gap="md"):
                                ui.avatar(initials="JD",
                                          color="primary",
                                          status="online")
                                with ui.vstack(gap="xs"):
                                    ui.text("Jane Doe",
                                            weight="bold")
                                    ui.text("jane@example.com",
                                            color="muted", size="sm")
                            with ui.dropdown(
                                trigger=ui.icon_button(
                                    "more-horizontal",
                                    variant="ghost",
                                    aria_label="Row actions"),
                                align="end",
                            ):
                                ui.dropdown_item(label="Edit",
                                                 icon_left="pencil")
                                ui.dropdown_item(label="Disable",
                                                 icon_left="user-x")
                                ui.dropdown_item(label="Delete",
                                                 icon_left="trash-2",
                                                 color="error")

                    ui.heading("Header avatar menu", level=3)
                    with ui.hstack(justify="end"):
                        with ui.dropdown(
                            trigger=ui.avatar(initials="AL",
                                              color="primary",
                                              status="online"),
                            align="end",
                        ):
                            ui.dropdown_item(label="Profile",
                                             icon_left="user")
                            ui.dropdown_item(label="Settings",
                                             icon_left="settings")
                            ui.dropdown_item(label="Sign out",
                                             icon_left="log-out",
                                             color="error")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Trigger carries ``aria-haspopup=\"menu\"`` + "
                        "``aria-expanded``. Panel emits "
                        "``role=\"menu\"`` ; items use "
                        "``role=\"menuitem\"``. Keyboard works : Tab "
                        "to focus the trigger, Space/Enter to "
                        "open, arrow keys to navigate items, Enter "
                        "to pick, Escape to close.",
                        color="muted", size="sm",
                    )
                    with ui.dropdown(
                        trigger=ui.button("A11y demo",
                                          icon_left="keyboard"),
                        aria_label="Demo actions",
                    ):
                        ui.dropdown_item(label="Item 1",
                                         icon_left="check")
                        ui.dropdown_item(label="Item 2",
                                         icon_left="check")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every Dropdown prop AND every escape hatch "
                        "is wired to a control ; the preview AND "
                        "the emitted HTML both refresh on every "
                        "change.",
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
                        "Mirror of Dropdown's ``BINDABLE_PROPS = "
                        "('open',)`` contract. The switch below is "
                        "bound to the SAME flag the dropdown reads — "
                        "toggling it opens/closes the panel with no "
                        "network round-trip, no ``.open()``/``.close()`` "
                        "call involved. Trigger / position / align / "
                        "dismissible stay design-time.",
                        color="muted", size="sm",
                    )
                    client = DropdownClient(key="playground")
                    with ui.flex(justify="center", align="center"):
                        ui.switch(label="Open", checked=client.open)

                    ui.divider()

                    with ui.flex(justify="center", classes="min-h-32"):
                        with ui.dropdown(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                            open=client.open,
                        ):
                            ui.dropdown_item(label="Item A")
                            ui.dropdown_item(label="Item B")

                    ui.divider()

                    preview = ui.dropdown(open=client.open)
                    with preview:
                        ui.dropdown_item(label="A")
                        ui.dropdown_item(label="B")
                    emitted_html_block(
                        "Emitted HTML — bz-show reads the bound "
                        "open path directly ; the switch writes "
                        "through it, no round-trip.",
                        serialize_html(preview),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (a button opens the menu, an "
                        "inner item closes it) played three ways. "
                        "Pick the mode that fits your need : imperative "
                        "for purely-visual triggers, binding when "
                        "another component needs to read the open "
                        "state, both together when you want write-"
                        "through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The dropdown owns its open "
                        "flag in client scope. ``.open()`` / "
                        "``.close()`` / ``.toggle()`` dispatch DOM "
                        "events caught by the dropdown root. **Use "
                        "this by default for menus — it's the "
                        "natural style for purely-visual state.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        with ui.dropdown(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                        ) as m1:
                            ui.dropdown_item(label="Item A")
                            ui.dropdown_item(label="Item B")
                            ui.dropdown_item(
                                label="Close from inside",
                                icon_left="x",
                                on_click=m1.close(),
                            )
                        ui.button("Open", on_click=m1.open())
                        ui.button("Toggle",
                                  variant="outline",
                                  on_click=m1.toggle())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading("Mode 2 — ClientBinding only",
                               level=3)
                    ui.text(
                        "Use this when **another component needs to "
                        "read or react to the open state** — a switch "
                        "that mirrors it, a badge that shows when "
                        "it's open, server-side awareness on the "
                        "next render. The binding is the single "
                        "source of truth multi-composant.",
                        color="muted", size="sm",
                    )
                    bound = DropdownClient(key="binding_only")
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        ui.switch(checked=bound.open)
                        with ui.dropdown(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                            open=bound.open,
                        ):
                            ui.dropdown_item(label="Item A")
                            ui.dropdown_item(label="Item B")
                            ui.dropdown_item(
                                label="Close from inside",
                                icon_left="x",
                                on_click=bound.open.set(False),
                            )
                        ui.button("Open via binding.set(True)",
                                  on_click=bound.open.set(True))

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        'A binding supplied AND ``.open()`` called on the'
                            ' instance. The framework detects the binding and'
                            ' delegates to ``binding.set(True)`` — **the DOM '
                            'dispatch is not used**, the single source of '
                            'truth is preserved. The switch and the '
                            'imperative buttons converge on the same flag.',
                        color="muted", size="sm",
                    )
                    both = DropdownClient(key="both")
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        ui.switch(checked=both.open)
                        with ui.dropdown(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                            open=both.open,
                        ) as m3:
                            ui.dropdown_item(label="Item A")
                            ui.dropdown_item(label="Item B")
                            ui.dropdown_item(
                                label="Close via dd.close()",
                                icon_left="x",
                                on_click=m3.close(),
                            )
                        ui.button("Open via dd.open()",
                                  on_click=m3.open())
                        ui.button("Toggle via dd.toggle()",
                                  variant="outline",
                                  on_click=m3.toggle())

                    ui.divider()

                    preview = ui.dropdown(open=bound.open)
                    with preview:
                        ui.dropdown_item(label="A")
                        ui.dropdown_item(label="B")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-show on the panel reads the bound state ; "
                        "binding.set / binding.toggle drive the "
                        "writes.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Open / close / item-click events wired "
                            "to client expressions. Zero network.",
                            color="muted", size="sm")
                    cevents = DropdownClientEvents()
                    with ui.flex(justify="center", classes="min-h-32"):
                        with ui.dropdown(
                            trigger=ui.button("Open client logger"),
                            on_open=cevents.log.push("open"),
                            on_close=cevents.log.push("close"),
                        ):
                            ui.dropdown_item(
                                label="Item A",
                                on_click=cevents.log.push("pick:A"))
                            ui.dropdown_item(
                                label="Item B",
                                on_click=cevents.log.push("pick:B"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.DropdownClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.dropdown(
                        trigger=ui.button("Open client logger"),
                        on_open=cevents.log.push("open"),
                        on_close=cevents.log.push("close"),
                    )
                    with preview:
                        ui.dropdown_item(
                            label="Item A",
                            on_click=cevents.log.push("pick:A"))
                    emitted_html_block(
                        "Emitted HTML — @bz-opened / @bz-closed on "
                        "the root ; per-item bz-on:click on each "
                        "DropdownItem. client expressions push the "
                        "event name onto the bound list.",
                        serialize_html(preview),
                    )
