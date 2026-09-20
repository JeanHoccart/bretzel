"""``Drawer`` test bench.

Ten cards : full 7-section gabarit. ``BINDABLE_PROPS = ("open",)`` —
same shape as Dialog ; the open flag gets a dedicated Client
playground card ; title / side / width / dismissible / persistent
stay design-time.

Five props : ``open`` / ``title`` / ``side`` / ``width`` /
``dismissible`` / ``persistent``. Two events : ``open`` / ``close``.
The drawer is purely visual — open it from outside via the imperative
API (``.open()`` / ``.close()`` / ``.toggle()``) or by binding
``open=`` to a ``ClientState`` field. Header / body / footer are
composed inside the ``with`` block.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/drawer"


SIDES  = ["left", "right", "top", "bottom"]
WIDTHS = ["sm", "md", "lg", "xl", "full"]


class DrawerPlayground(PageState):
    title:       str  = field(default="Navigation")
    side:        str  = field(default="right")
    width:       str  = field(default="md")
    dismissible: bool = field(default=True)
    persistent:  bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class DrawerEvents(PageState):
    log: list = field(default_factory=list)


class DrawerClient(ClientState, persist="memory"):
    open: bool = field(default=False)


class DrawerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = DrawerEvents()
    state.log = [*state.log, name]


def log_open()  -> None: log("open")
def log_close() -> None: log("close")


def clear_log() -> None:
    state = DrawerEvents()
    state.log = []


def server_changed(state: DrawerPlayground) -> None:
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


def build_preview(state: DrawerPlayground) -> dict:
    kwargs: dict = {
        "title": state.title,
        "side": state.side,
        "width": state.width,
        "dismissible": state.dismissible,
        "persistent": state.persistent,
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


@refreshable(deps=[DrawerPlayground])
def server_panel() -> None:
    state = DrawerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("title"):
            ui.input(value=state.title,
                     placeholder="Navigation",
                     on_change=server_changed)
        with control("side"):
            ui.select(value=state.side,
                      options=[(s, s) for s in SIDES],
                      on_change=server_changed)
        with control("width (perpendicular to anchor)"):
            ui.select(value=state.width,
                      options=[(w, w) for w in WIDTHS],
                      on_change=server_changed)
        with control("dismissible"):
            ui.switch(checked=state.dismissible,
                      on_change=server_changed)
        with control("persistent (overrides dismissible)"):
            ui.switch(checked=state.persistent,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!shadow-2xl",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-drawer",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Navigation drawer",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="--bz-overlay-z: 100",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=drawer",
                        on_change=server_changed)
        with control("tooltip (wraps drawer root)"):
            ui.input(value=state.tooltip,
                     placeholder="Open navigation",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        with ui.drawer(**kwargs) as preview_drw:
            ui.text("This is the drawer body. Toggle the controls "
                    "above to see the panel reshape.",
                    color="muted")
        ui.button("Open the preview drawer", color="primary",
                  on_click=preview_drw.open())

    ui.divider()

    preview = ui.drawer(**kwargs)
    with preview:
        ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Drawer with body only — open via .open())",
        serialize_html(preview),
    )


@refreshable(deps=[DrawerEvents])
def events_panel() -> None:
    state = DrawerEvents()

    ui.text(
        "Drawer exposes two events : ``on_open`` and ``on_close`` — "
        "both wired to the server on the same drawer (the close handler "
        "rides a hidden carrier). Open / close below and watch the log "
        "update on both.",
        color="muted", size="sm",
    )

    with ui.flex(justify="center"):
        with ui.drawer(
            title="Event-logging drawer",
            on_open=log_open,
            on_close=log_close,
        ) as logger_drw:
            ui.text("Close via the × or click outside. Both fire "
                    "``on_close``.",
                    color="muted")
        ui.button("Open + close logger", color="primary",
                  on_click=logger_drw.open())

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
        ui.text("(no events yet — open and close the drawer above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.drawer(
        title="Sample",
        on_open=log_open,
        on_close=log_close,
    )
    with representative:
        ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Drawer with on_open + on_close)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Drawer", level=1)
            ui.text(
                "Side-anchored sliding panel. Same architecture as "
                "Dialog (backdrop + escape + body scroll lock + "
                "bound-open contract) but the panel slides in from "
                "one of the four screen edges instead of centring. "
                "Two ways to drive the open state : ``as drw`` + "
                "``drw.open()`` (imperative API — default for "
                "purely-visual overlays), or ``open=ClientBinding`` "
                "(when another component needs to read or react to "
                "the state). The 2 modes are compared side-by-side "
                "in Card 9.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Click each trigger to see the drawer.",
                            color="muted", size="sm")

                    ui.heading("Basic — imperative API", level=3)
                    ui.text(
                        "Capture the instance via ``as drw`` and call "
                        "``drw.open()`` / ``drw.close()`` / "
                        "``drw.toggle()`` from any sibling — client-"
                        "local state, no ClientState declared. The "
                        "imperative API is the default style for "
                        "purely-visual overlays.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md"):
                        with ui.drawer(title="A drawer") as basic_drw:
                            ui.text("Triggered from the sibling button.")
                            ui.button(
                                "Close from inside",
                                variant="ghost",
                                on_click=basic_drw.close(),
                            )
                        ui.button(
                            "Open via .open()",
                            on_click=basic_drw.open(),
                        )
                        ui.button(
                            "Toggle via .toggle()",
                            variant="outline",
                            on_click=basic_drw.toggle(),
                        )

                    ui.heading("Sides", level=3)
                    with ui.hstack(wrap=True):
                        for s in SIDES:
                            with ui.drawer(title=f"Side: {s}",
                                           side=s) as side_drw:
                                ui.text(f"Drawer slides in from "
                                        f"the {s}.",
                                        color="muted")
                            ui.button(s.title(),
                                      on_click=side_drw.open())

                    ui.heading("Widths (perpendicular dimension)",
                               level=3)
                    with ui.hstack(wrap=True):
                        for w in WIDTHS:
                            with ui.drawer(title=f"Width {w}",
                                           width=w) as width_drw:
                                ui.text(f"This drawer uses "
                                        f"width={w}.")
                            ui.button(w.upper(),
                                      on_click=width_drw.open())

                    ui.heading("Dismissible vs persistent", level=3)
                    with ui.hstack():
                        with ui.drawer(title="Dismissible") as dism_drw:
                            ui.text("Backdrop / ESC close.",
                                    color="muted")
                        ui.button("Dismissible (default)",
                                  on_click=dism_drw.open())
                        with ui.drawer(title="Persistent",
                                       persistent=True) as pers_drw:
                            ui.text("Only an explicit button "
                                    "dismisses.",
                                    color="muted")
                            ui.button("Close",
                                      variant="ghost",
                                      on_click=pers_drw.close())
                        ui.button("Persistent", color="error",
                                  on_click=pers_drw.open())

            # ── Card 2 — Composition ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composition", level=2)
                    ui.text(
                        "Header / body / footer are all composed "
                        "inside the ``with`` block — the drawer owns "
                        "the chrome (title / close button / panel) "
                        "and you fill the body. Open from any "
                        "sibling via the imperative API.",
                        color="muted", size="sm",
                    )

                    ui.heading("Triggered by an IconButton", level=3)
                    with ui.drawer(title="Menu",
                                   side="left") as menu_drw:
                        with ui.vstack():
                            ui.link("Home",     href="#")
                            ui.link("Projects", href="#")
                            ui.link("Settings", href="#")
                    ui.icon_button("menu",
                                   variant="ghost",
                                   aria_label="Menu",
                                   on_click=menu_drw.open())

                    ui.heading("Footer composed in the body", level=3)
                    with ui.hstack(align="center", gap="md"):
                        with ui.drawer(title="Save changes?") as save_drw:
                            ui.text("Footer pinned at the bottom of "
                                    "the panel.")
                            with ui.hstack(justify="end"):
                                ui.button("Save", color="primary",
                                          on_click=save_drw.close())
                        ui.button("With footer", variant="outline",
                                  on_click=save_drw.open())

                    ui.heading(
                        "open = ClientBinding — see Card 9",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading('dismissible=False — there is no way OUT any more',
                               level=3)
                    ui.text(
                        'The same cut as the dialog: neither Escape nor a'
                            ' click on the veil. The drawer must then offer '
                            'its own way out, failing which there is none.',
                        color="muted", size="xs",
                    )
                    with ui.drawer(title='Mandatory step',
                                   dismissible=False) as locked_drw:
                        ui.text("Choisissez avant de continuer.")
                        ui.button("Terminer",
                                  on_click=locked_drw.close())
                    ui.button("dismissible=False",
                              on_click=locked_drw.open())

                    ui.heading("No title", level=3)
                    with ui.drawer() as notitle_drw:
                        ui.text("Just body content.")
                    ui.button("Title-less",
                              on_click=notitle_drw.open())

                    ui.heading("Bottom drawer (mobile sheet)", level=3)
                    with ui.drawer(title="Pick an action",
                                   side="bottom") as sheet_drw:
                        with ui.vstack():
                            ui.button("Share",  variant="ghost",
                                      icon_left="share")
                            ui.button("Save",   variant="ghost",
                                      icon_left="save")
                            ui.button("Delete", variant="ghost",
                                      color="error",
                                      icon_left="trash-2")
                    ui.button("Bottom sheet", variant="outline",
                              on_click=sheet_drw.open())

                    ui.heading("Long scrolling body", level=3)
                    with ui.drawer(title="Lots of text") as long_drw:
                        for i in range(1, 21):
                            ui.text(f"Paragraph {i} — Lorem ipsum.",
                                    color="muted")
                    ui.button("Long body",
                              on_click=long_drw.open())

                    ui.heading("HTML-special title (XSS escape)",
                               level=3)
                    with ui.drawer(
                        title="<script>alert(1)</script>",
                    ) as xss_drw:
                        ui.text("Framework escapes the title.")
                    ui.button("XSS title",
                              on_click=xss_drw.open())

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Common drawer patterns.",
                            color="muted", size="sm")

                    ui.heading("Mobile navigation (left drawer)",
                               level=3)
                    with ui.drawer(title="Bretzel",
                                   side="left") as nav_drw:
                        with ui.vstack(gap="sm"):
                            ui.heading("Sections", level=4,
                                       color="muted", size="xs")
                            ui.link("Home",        href="/")
                            ui.link("Components",  href="/")
                            ui.link("Themes",      href="/")
                            ui.divider()
                            ui.heading("Help", level=4,
                                       color="muted", size="xs")
                            ui.link("Docs",      href="/")
                            ui.link("Discord",   href="/", external=True)
                    ui.icon_button("menu",
                                   variant="ghost",
                                   aria_label="Open nav",
                                   on_click=nav_drw.open())

                    ui.heading("Filters panel (right drawer)", level=3)
                    with ui.drawer(title="Filter projects",
                                   side="right") as filters_drw:
                        with ui.vstack():
                            ui.checkbox(label="Open issues",
                                        checked=True)
                            ui.checkbox(label="Archived")
                            ui.checkbox(label="Has draft PR")
                            with ui.form_field(label="Owner"):
                                ui.input(placeholder="@user")
                            with ui.hstack(justify="end"):
                                ui.button("Apply", color="primary",
                                          on_click=filters_drw.close())
                    ui.button("Filters",
                              icon_left="filter",
                              variant="outline",
                              on_click=filters_drw.open())

                    ui.heading("Side-by-side details (right drawer + "
                               "preview)", level=3)
                    with ui.drawer(title="Project details",
                                   side="right",
                                   width="xl") as details_drw:
                        with ui.vstack():
                            ui.heading("Aurora", level=3)
                            ui.text("Long description body.",
                                    color="muted")
                    ui.button("Open details",
                              on_click=details_drw.open())

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Panel emits ``role=\"dialog\"`` + "
                        "``aria-modal=\"true\"`` (same semantics as "
                        "Dialog). Pair with ``aria_label=`` when the "
                        "title alone doesn't describe the drawer's "
                        "purpose. Focus auto-lands on the first "
                        "interactive child.",
                        color="muted", size="sm",
                    )
                    with ui.drawer(
                        title="Settings",
                        aria_label="Settings drawer",
                    ) as a11y_drw:
                        with ui.form_field(label="Type something"):
                            ui.input(placeholder="Auto-focused")
                    ui.button("Keyboard test",
                              icon_left="keyboard",
                              on_click=a11y_drw.open())

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
                        "Mirror of Drawer's ``BINDABLE_PROPS = "
                        "('open',)`` contract. The switch below is "
                        "bound to the SAME flag the drawer reads — "
                        "toggling it opens/closes the drawer with no "
                        "network round-trip, no ``.open()``/``.close()`` "
                        "call involved. Title / side / width / "
                        "dismissible / persistent stay design-time.",
                        color="muted", size="sm",
                    )
                    client = DrawerClient(key="playground")
                    with ui.flex(justify="center", align="center"):
                        ui.switch(label="Open", checked=client.open)

                    ui.divider()

                    with ui.flex(justify="center"):
                        with ui.drawer(open=client.open,
                                       title="Client-bound drawer"):
                            ui.text(
                                "Bound to the switch above via "
                                "ClientBinding — close via ESC, "
                                "backdrop, or flipping the switch.",
                                color="muted",
                            )

                    ui.divider()

                    preview = ui.drawer(open=client.open,
                                         title="Client-bound drawer")
                    with preview:
                        ui.text("Body", color="muted")
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
                        "Same scenario (a button opens the drawer, an "
                        "inner button closes it) played three ways. "
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
                        "No ClientState. The drawer owns its open "
                        "flag in client scope. ``.open()`` / "
                        "``.close()`` / ``.toggle()`` dispatch DOM "
                        "events caught by the drawer root. **Use "
                        "this by default for overlays — it's the "
                        "natural style for purely-visual state.**",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md"):
                        with ui.drawer(title="Imperative",
                                       side="right") as m1:
                            ui.text("client-local, zero ClientState.",
                                    color="muted")
                            ui.button("Close",
                                      variant="ghost",
                                      on_click=m1.close())
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
                    bound = DrawerClient(key="binding_only")
                    with ui.hstack(align="center", gap="md"):
                        ui.switch(checked=bound.open)
                        with ui.drawer(open=bound.open,
                                       title="Bound",
                                       side="right"):
                            ui.text("The switch above is the binding "
                                    "in action — it reads + writes "
                                    "the same flag this drawer reads.",
                                    color="muted")
                            ui.button("Close from inside",
                                      variant="ghost",
                                      on_click=bound.open.set(False))
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
                    both = DrawerClient(key="both")
                    with ui.hstack(align="center", gap="md"):
                        ui.switch(checked=both.open)
                        with ui.drawer(open=both.open,
                                       title="Both",
                                       side="right") as m3:
                            ui.text("Both paths converge on the "
                                    "binding.",
                                    color="muted")
                            ui.button("Close via drw.close()",
                                      variant="ghost",
                                      on_click=m3.close())
                        ui.button("Open via drw.open()",
                                  on_click=m3.open())
                        ui.button("Toggle via drw.toggle()",
                                  variant="outline",
                                  on_click=m3.toggle())

                    ui.divider()

                    preview = ui.drawer(open=bound.open,
                                        title="Bound drawer",
                                        side="right")
                    with preview:
                        ui.text("Body")
                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-show reads the bound path ; toggle / set "
                        "on the binding write back without a round-"
                        "trip.",
                        serialize_html(preview),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("Open / close events wired to client "
                            "expressions that push onto a "
                            "ClientState list. Zero network.",
                            color="muted", size="sm")
                    cevents = DrawerClientEvents()
                    with ui.flex(justify="center"):
                        with ui.drawer(
                            title="Client events demo",
                            on_open=cevents.log.push("open"),
                            on_close=cevents.log.push("close"),
                        ) as ce_drw:
                            ui.text("Close me — the runtime pushes "
                                    "'close' to the local log.",
                                    color="muted")
                        ui.button("Open client-event logger",
                                  on_click=ce_drw.open())

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no "
                                "refresh)", color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.DrawerClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.drawer(
                        title="Client events demo",
                        on_open=cevents.log.push("open"),
                        on_close=cevents.log.push("close"),
                    )
                    with preview:
                        ui.text("Body")
                    emitted_html_block(
                        "Emitted HTML — @bz-opened / @bz-closed "
                        "listeners on the root ; client expressions "
                        "push the event name onto the bound list.",
                        serialize_html(preview),
                    )
