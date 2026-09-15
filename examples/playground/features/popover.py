"""``Popover`` test bench.

Ten visual cards : full gabarit. ``BINDABLE_PROPS = ("open",)`` —
the open flag is bindable ; position / align / dismissible stay
design-time.

Props : ``trigger`` (Component) / ``open`` / ``position`` / ``align``
/ ``dismissible``. Two events : ``open`` / ``close``. No arrow.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/popover"


POSITIONS = ["top", "bottom", "left", "right"]
ALIGNS    = ["start", "center", "end"]


class PopoverPlayground(PageState):
    position:    str  = field(default="bottom")
    align:       str  = field(default="center")
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


class PopoverEvents(PageState):
    log: list = field(default_factory=list)


class PopoverClient(ClientState, persist="memory"):
    open: bool = field(default=False)


class PopoverClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = PopoverEvents()
    state.log = [*state.log, name]


def log_open()  -> None: log("open")
def log_close() -> None: log("close")


def clear_log() -> None:
    state = PopoverEvents()
    state.log = []


def server_changed(state: PopoverPlayground) -> None:
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


def build_preview(state: PopoverPlayground) -> dict:
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


@refreshable(deps=[PopoverPlayground])
def server_panel() -> None:
    state = PopoverPlayground()

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
                     placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-popover",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Helpful explanation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 280px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=popover",
                        on_change=server_changed)
        with control("tooltip (on trigger)"):
            ui.input(value=state.tooltip,
                     placeholder="Open the popover",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center", classes="min-h-32"):
        with ui.popover(
            trigger=ui.button("Open preview popover",
                              color="primary"),
            **kwargs,
        ):
            ui.text("This is the popover content. Toggle controls "
                    "above to see the panel reshape.",
                    color="muted")

    ui.divider()

    preview = ui.popover(
        trigger=ui.button("Open preview popover", color="primary"),
        **kwargs,
    )
    with preview:
        ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Popover + body)",
        serialize_html(preview),
    )


@refreshable(deps=[PopoverEvents])
def events_panel() -> None:
    state = PopoverEvents()

    ui.text(
        "Popover fires ``on_open`` AND ``on_close`` — both to the "
        "server. The second handler rides a hidden carrier "
        "(``hx-trigger=\"close from:#<root>\"``). Open / close below "
        "and watch the log update on both.",
        color="muted", size="sm",
    )

    with ui.flex(justify="center", classes="min-h-32"):
        with ui.popover(
            trigger=ui.button("Open + close logger",
                              color="primary"),
            on_open=log_open,
            on_close=log_close,
        ):
            ui.text("Click outside or press Escape to close.",
                    color="muted")

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
        ui.text("(no events yet — open and close the popover above)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.popover(
        trigger=ui.button("Open", color="primary"),
        on_open=log_open,
        on_close=log_close,
    )
    with representative:
        ui.text("Body")
    emitted_html_block(
        "Emitted HTML (Popover with on_open + on_close — note the "
        "hidden close carrier with hx-trigger=\"close from:#…\")",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Popover", level=1)
            ui.text(
                "Anchored floating panel toggled by a trigger. "
                "Pure client-side — no runtime helper. Click-outside and "
                "Escape dismiss by default. Same ``open=`` contract "
                "as Dialog / Drawer / Dropdown. Three ways to drive "
                "the open state : ``trigger=`` built-in (simplest), "
                "``as p`` + ``p.open()`` (imperative API — default "
                "for purely-visual overlays), or ``open=ClientBinding`` "
                "(when another component needs to read or react to "
                "the state). The 3 modes are compared side-by-side "
                "in Card 9.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Click each trigger to see the panel.",
                            color="muted", size="sm")

                    ui.heading("Basic — trigger= built-in", level=3)
                    ui.text(
                        "Simplest path : pass a ``trigger=`` component "
                        "and the popover wires its ``bz-on:click`` for you. "
                        "Zero state, zero variable to capture.",
                        color="muted", size="sm",
                    )
                    with ui.popover(
                        trigger=ui.button("Open popover"),
                    ):
                        ui.text("Default position bottom, "
                                "centre-aligned.")

                    ui.heading(
                        "Basic — external trigger via .open()",
                        level=3,
                    )
                    ui.text(
                        "Same popover, opened from a sibling button. "
                        "Capture the instance via ``as p`` and call "
                        "``p.open()`` / ``p.close()`` — client-local "
                        "state, no ClientState declared. The popover "
                        "still needs a visual anchor for positioning, "
                        "so we keep a small ``Anchor`` trigger — both "
                        "the built-in click and the external buttons "
                        "write to the same open flag.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        with ui.popover(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                        ) as basic_pop:
                            ui.text("Triggered from the sibling "
                                    "button.")
                            ui.button(
                                "Close from inside",
                                variant="ghost",
                                on_click=basic_pop.close(),
                            )
                        ui.button(
                            "Open via .open()",
                            on_click=basic_pop.open(),
                        )
                        ui.button(
                            "Toggle via .toggle()",
                            variant="outline",
                            on_click=basic_pop.toggle(),
                        )

                    ui.heading("Positions", level=3)
                    with ui.hstack(wrap=True, classes="min-h-32"):
                        for p in POSITIONS:
                            with ui.popover(
                                trigger=ui.button(p.title()),
                                position=p,
                            ):
                                ui.text(f"Popover anchored {p}.",
                                        color="muted")

                    ui.heading("Alignments", level=3)
                    with ui.hstack(wrap=True, classes="min-h-32"):
                        for a in ALIGNS:
                            with ui.popover(
                                trigger=ui.button(a.title()),
                                align=a,
                            ):
                                ui.text(f"align={a}",
                                        color="muted")

                    ui.heading("Dismissible", level=3)
                    with ui.hstack(wrap=True, classes="min-h-32"):
                        with ui.popover(
                            trigger=ui.button("dismissible=True (default)"),
                        ):
                            ui.text("Click outside or Escape to close.",
                                    color="muted")
                        with ui.popover(
                            trigger=ui.button("dismissible=False",
                                              color="error"),
                            dismissible=False,
                        ):
                            ui.text("Only an explicit close dismisses.",
                                    color="muted")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Two slots : ``trigger`` (Component) and "
                        "the ``with`` block holding panel content. "
                        "Content can be anything — text, form, "
                        "stack of buttons.",
                        color="muted", size="sm",
                    )

                    ui.heading("trigger = Button", level=3)
                    with ui.popover(
                        trigger=ui.button("Open via Button"),
                    ):
                        ui.text("Most common shape.")

                    ui.heading("trigger = IconButton", level=3)
                    with ui.popover(
                        trigger=ui.icon_button("info",
                                               variant="ghost",
                                               aria_label="Info"),
                    ):
                        ui.text("Concise info panel.",
                                color="muted")

                    ui.heading("Content = rich layout", level=3)
                    with ui.popover(
                        trigger=ui.button("Profile preview"),
                    ):
                        with ui.vstack():
                            with ui.hstack(align="center", gap="sm"):
                                ui.avatar(initials="AL",
                                          color="primary",
                                          status="online")
                                with ui.vstack(gap="xs"):
                                    ui.text("Ada Lovelace",
                                            weight="bold")
                                    ui.text("Online",
                                            color="muted", size="sm")
                            ui.divider()
                            ui.button("View profile",
                                      variant="ghost",
                                      icon_left="arrow-right")

                    ui.heading(
                        "open = ClientBinding — see Card 9 mode 2",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty panel", level=3)
                    with ui.popover(
                        trigger=ui.button("Empty"),
                    ):
                        pass

                    ui.heading("Very long content (scrolling)",
                               level=3)
                    with ui.popover(
                        trigger=ui.button("Long content"),
                    ):
                        with ui.vstack():
                            for i in range(1, 21):
                                ui.text(f"Line {i} — lorem ipsum.",
                                        color="muted")

                    ui.heading("Persistent (no click-outside dismiss)",
                               level=3)
                    with ui.popover(
                        trigger=ui.button("Persistent",
                                          color="error"),
                        dismissible=False,
                    ):
                        ui.text("Click-outside is inert. Press the "
                                "trigger to toggle.",
                                color="muted")

                    ui.heading("Nested popovers (anti-pattern)",
                               level=3)
                    ui.text(
                        "Possible but rarely a good idea — both "
                        "respect click-outside, so the outer one "
                        "may close when the inner opens.",
                        color="muted", size="xs",
                    )
                    with ui.popover(
                        trigger=ui.button("Outer popover"),
                    ):
                        with ui.vstack():
                            ui.text("Inner :")
                            with ui.popover(
                                trigger=ui.button("Inner"),
                            ):
                                ui.text("Inner panel content.")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Popover patterns in the wild.",
                            color="muted", size="sm")

                    ui.heading("Help icon next to a label", level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.text("API key")
                        with ui.popover(
                            trigger=ui.icon_button(
                                "help-circle",
                                variant="ghost",
                                size="sm",
                                aria_label="Help",
                            ),
                        ):
                            ui.text(
                                "Your API key is generated at "
                                "first login and rotated every "
                                "90 days.",
                                size="sm", color="muted",
                            )

                    ui.heading("Mini form (filter / share)", level=3)
                    with ui.popover(
                        trigger=ui.button("Share",
                                          icon_left="share"),
                    ):
                        with ui.vstack():
                            with ui.form_field(label="Recipient email"):
                                ui.input(type="email", placeholder="ada@example.com")
                            ui.checkbox(label="Notify by email")
                            ui.button("Share", color="primary")

                    ui.heading("Confirmation prompt (light dialog)",
                               level=3)
                    with ui.popover(
                        trigger=ui.button("Delete row",
                                          color="error",
                                          icon_left="trash-2"),
                    ):
                        with ui.vstack():
                            ui.text("Delete this row ?",
                                    weight="bold")
                            ui.text("This cannot be undone.",
                                    color="muted", size="sm")
                            with ui.hstack(justify="end", gap="sm"):
                                ui.button("Cancel",
                                          variant="ghost")
                                ui.button("Delete",
                                          color="error")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Trigger carries ``aria-haspopup=\"dialog\"`` "
                        "+ ``aria-expanded``. Panel emits "
                        "``role=\"dialog\"`` so screen readers "
                        "announce it as a small interaction. Escape "
                        "globally closes regardless of focus.",
                        color="muted", size="sm",
                    )
                    with ui.popover(
                        trigger=ui.button("Keyboard test",
                                          icon_left="keyboard"),
                        aria_label="Demo popover",
                    ):
                        ui.text("Tab to focus controls inside. "
                                "Escape closes from anywhere.",
                                color="muted")
                        ui.button("Action", color="primary")

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
                        "Mirror of Popover's ``BINDABLE_PROPS = "
                        "('open',)`` contract. The switch below is "
                        "bound to the SAME flag the popover reads — "
                        "toggling it opens/closes the popover with no "
                        "network round-trip, no ``.open()``/``.close()`` "
                        "call involved. Trigger / position / align / "
                        "dismissible stay design-time.",
                        color="muted", size="sm",
                    )
                    client = PopoverClient(key="playground")
                    with ui.flex(justify="center", align="center"):
                        ui.switch(label="Open", checked=client.open)

                    ui.divider()

                    with ui.flex(justify="center", classes="min-h-32"):
                        with ui.popover(
                            trigger=ui.button("Trigger", color="primary"),
                            open=client.open,
                        ):
                            ui.text(
                                "Bound to the switch above via "
                                "ClientBinding — close via click-"
                                "outside, Escape, or flipping the "
                                "switch.",
                                color="muted",
                            )

                    ui.divider()

                    preview = ui.popover(
                        trigger=ui.button("Trigger", color="primary"),
                        open=client.open,
                    )
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
                        "Same scenario (a sibling button opens the "
                        "popover, an inner button closes it) played "
                        "three ways. Pick the mode that fits your "
                        "need : imperative for purely-visual triggers, "
                        "binding when another component needs to read "
                        "the open state, both together when you want "
                        "write-through.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only (default style) ────
                    ui.heading(
                        "Mode 1 — Imperative only (default)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The popover owns its open "
                        "flag in client scope. ``.open()`` / "
                        "``.close()`` / ``.toggle()`` dispatch DOM "
                        "events caught by the popover root. **Use "
                        "this by default for overlays — it's the "
                        "natural style for purely-visual state.** "
                        "Note : a popover needs a visual anchor to "
                        "position the panel, so we keep a tiny "
                        "``Anchor`` trigger alongside the external "
                        "buttons.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        with ui.popover(
                            trigger=ui.button("Anchor",
                                              variant="outline"),
                        ) as m1:
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
                    bound = PopoverClient(key="binding_only")
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        ui.switch(checked=bound.open)
                        with ui.popover(
                            trigger=ui.button("Popover trigger",
                                              color="primary"),
                            open=bound.open,
                        ):
                            ui.text("The switch above is the binding "
                                    "in action — it reads + writes "
                                    "the same flag this popover reads.",
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
                        "Binding fournie ET on appelle ``.open()`` "
                        "sur l'instance. Le framework détecte la "
                        "binding et délègue à ``binding.set(True)`` "
                        "— **le DOM dispatch n'est pas utilisé**, "
                        "single source of truth préservée. La switch "
                        "et les boutons imperatifs convergent sur "
                        "le même flag.",
                        color="muted", size="sm",
                    )
                    both = PopoverClient(key="both")
                    with ui.hstack(align="center", gap="md",
                                   classes="min-h-32"):
                        ui.switch(checked=both.open)
                        with ui.popover(
                            trigger=ui.button("Popover trigger",
                                              color="primary"),
                            open=both.open,
                        ) as m3:
                            ui.text("Both paths converge on the "
                                    "binding.",
                                    color="muted")
                            ui.button("Close via p.close()",
                                      variant="ghost",
                                      on_click=m3.close())
                        ui.button("Open via p.open()",
                                  on_click=m3.open())
                        ui.button("Toggle via p.toggle()",
                                  variant="outline",
                                  on_click=m3.toggle())

                    ui.divider()

                    preview = ui.popover(open=bound.open)
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
                            "expressions. Zero network.",
                            color="muted", size="sm")
                    cevents = PopoverClientEvents()
                    with ui.flex(justify="center", classes="min-h-32"):
                        with ui.popover(
                            trigger=ui.button("Open client logger"),
                            on_open=cevents.log.push("open"),
                            on_close=cevents.log.push("close"),
                        ):
                            ui.text("Close me — the runtime logs locally.",
                                    color="muted")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    ui.divider()

                    log_text = ClientExpression(
                        '($bz.state.PopoverClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    preview = ui.popover(
                        trigger=ui.button("Open client logger"),
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
