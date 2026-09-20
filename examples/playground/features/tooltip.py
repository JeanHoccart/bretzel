"""``Tooltip`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
("text",)`` — the panel text is bindable ; position / delay / color
stay design-time. No events.

Four props : ``text`` (positional, str | ClientBinding), ``position``,
``delay``, ``color``. Used as a context manager wrapping its trigger.
The arrow is always present (no toggle).
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/tooltip"


POSITIONS = ["top", "bottom", "left", "right"]
COLORS    = ["text", "primary", "secondary", "success",
             "warning", "error", "info", "muted"]


class TooltipPlayground(PageState):
    text:        str  = field(default="Helpful hint")
    position:    str  = field(default="top")
    delay:       int  = field(default=150)
    color:       str  = field(default="text")
    enabled:     bool = field(default=True)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifier (tooltip-as-modifier is the SAME component
    # so we only expose ``visible`` here, not a nested tooltip).
    visible:     str  = field(default="on")


class TooltipClient(ClientState, persist="memory"):
    """Mirror of Tooltip's BINDABLE_PROPS = ('text',).

    ``enabled`` is NOT in ``BINDABLE_PROPS`` but accepts a
    ``ClientBinding`` anyway (cf. the signature). This bench bound it
    nowhere — which is exactly why its reactivity could die in silence
    for two days. It is bound here, now.
    """

    text: str = field(default="Live hint — edit me")
    enabled: bool = field(default=True)


#: The panel text of the "Inside a zone that refreshes" card. Named
#: rather than written in the clear: ``tests/probes/probe_tooltip.py``
#: READS it here to find the teleported panel, and two literals would
#: diverge — it is manual copying that killed four probes on
#: 2026-08-30.
REFRESHED_ZONE_TIP = 'This panel must hide AFTER the click'


class RefreshedZone(PageState):
    """The state of the zone that refreshes under the tooltip.

    A single counter: what matters is not what it shows but the fact
    that clicking it REPLACES the subtree the trigger lives in.
    """

    clicks: int = field(default=0)


def bump(state: RefreshedZone) -> None:
    state.clicks += 1


@refreshable(deps=[RefreshedZone])
def tooltip_in_a_refreshed_zone() -> None:
    """The trigger is INSIDE the zone its own click refreshes.

    Why this card exists. A tooltip's panel is **teleported** under
    ``<body>``: so it does not live in the subtree the morph replaces. If
    the new trigger does not find its panel again, the panel stays shown
    for ever — a rectangle of text stuck to the screen that nothing can
    close any more.

    It is a REAL regression, fixed on 2026-08-19. Its guard rail
    (``tests/probes/probe_tooltip.py``) drove a bench that was deleted
    with the ``/matrix`` family on 2026-08-30, and the "it hides after a
    morph" half has been bare since. This card dresses it again — and it
    belongs here anyway: no bench showed a tooltip inside a refreshable
    zone, although it is a toolbar's ordinary configuration.
    """
    state = RefreshedZone()
    with ui.hstack(align="center"):
        with ui.tooltip(REFRESHED_ZONE_TIP):
            ui.button('Refresh the zone', id="tip-refresh-trigger",
                      icon_left="refresh-cw", on_click=bump)
        ui.text(f"{state.clicks}' refresh(es)'",
                color="muted", size="sm")


def server_changed(state: TooltipPlayground) -> None:
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


def build_preview(state: TooltipPlayground) -> dict:
    kwargs: dict = {
        "position": state.position,
        "delay": int(state.delay or 0),
        "color": state.color,
        "enabled": state.enabled,
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
    if state.visible == "off":
        kwargs["visible"] = False
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[TooltipPlayground])
def server_panel() -> None:
    state = TooltipPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("text"):
            ui.input(value=state.text,
                     placeholder="Helpful hint",
                     on_change=server_changed)
        with control("position"):
            ui.select(value=state.position,
                      options=[(p, p) for p in POSITIONS],
                      on_change=server_changed)
        with control("delay (ms)"):
            ui.number_input(value=state.delay,
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("enabled"):
            ui.switch(checked=state.enabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-tooltip",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Help text",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="font-style: italic",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=tooltip",
                        on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center", align="center", classes="min-h-24"):
        with ui.tooltip(state.text, **kwargs):
            ui.button("Hover me", variant="outline")

    ui.divider()

    preview = ui.tooltip(state.text, **kwargs)
    with preview:
        ui.button("Hover me", variant="outline")
    emitted_html_block(
        "Emitted HTML (wrapper + panel + trigger)",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Tooltip", level=1)
            ui.text(
                "Hover-/focus-revealed text panel. Wraps its trigger "
                "via a ``with`` block (or the universal "
                "``tooltip=`` modifier kwarg on any component). "
                "Pure client-side — no network round-trip. The Server "
                "playground card stress-tests every prop ; the "
                "emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Hover each button to see the tooltip.",
                            color="muted", size="sm")

                    ui.heading("Positions", level=3)
                    with ui.hstack(gap="lg"):
                        for p in POSITIONS:
                            with ui.tooltip(f"Tooltip on {p}",
                                            position=p):
                                ui.button(p.title())

                    ui.heading("Delay (ms before showing)", level=3)
                    with ui.hstack():
                        with ui.tooltip("Instant — delay=0", delay=0):
                            ui.button("0ms")
                        with ui.tooltip('Default — delay=150',
                                        delay=150):
                            ui.button("300ms")
                        with ui.tooltip("Lazy — delay=1000",
                                        delay=1000):
                            ui.button("1000ms")

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS[1:]:  # skip "text" (default)
                            with ui.tooltip(f"{c.title()} tooltip",
                                            color=c):
                                ui.button(c.title(), color=c,
                                          variant="soft")

                    ui.heading("Enabled (hover/focus reveal gate)",
                               level=3)
                    with ui.hstack(gap="lg"):
                        with ui.tooltip("You'll see this one",
                                        enabled=True):
                            ui.button("enabled=True (default)")
                        with ui.tooltip("You'll never see this",
                                        enabled=False):
                            ui.button("enabled=False")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "One reactive slot : ``text`` (positional). "
                        "Accepts str or ClientBinding (the runtime swaps "
                        "via ``bz-text`` on the panel).",
                        color="muted", size="sm",
                    )

                    ui.heading("text=str", level=3)
                    with ui.hstack():
                        with ui.tooltip("Static text"):
                            ui.button("Hover")

                    ui.heading(
                        "text=ClientBinding — see Client playground",
                        level=3,
                    )
                    ui.text(
                        "Bind to a ClientState string ; the panel "
                        "text reflects state mutations without a "
                        "round-trip.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs that historically break.",
                            color="muted", size="sm")

                    ui.heading("Empty text", level=3)
                    with ui.hstack():
                        with ui.tooltip(""):
                            ui.button("Hover (empty tooltip)")

                    ui.heading("Very long text (250 chars)", level=3)
                    with ui.hstack():
                        with ui.tooltip("A" * 250):
                            ui.button("Hover (long)")

                    ui.heading("Emoji + multi-script", level=3)
                    with ui.hstack():
                        with ui.tooltip("Ship 🚀 — שלום — 中文"):
                            ui.button("Hover (mixed)")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the text — the script "
                        "renders as literal text instead of "
                        "executing.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        with ui.tooltip("<script>alert(1)</script>"):
                            ui.button("Hover (XSS attempt)")

                    ui.heading("Universal modifier form — "
                               "tooltip=str on any component", level=3)
                    ui.text(
                        "Every Bretzel component accepts a "
                        "``tooltip=`` kwarg ; the framework wraps "
                        "the rendered output in a Tooltip with the "
                        "same panel.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        ui.button("Save", tooltip="Save the document",
                                  icon_left="save")
                        ui.badge("3", color="error",
                                 tooltip="3 unread items")
                        ui.icon("info", color="info",
                                tooltip="Help text on an icon")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Tooltip wraps any trigger.",
                            color="muted", size="sm")

                    ui.heading("On ui.button", level=3)
                    with ui.hstack():
                        with ui.tooltip("Reclaim 30% of your quota"):
                            ui.button("Free up space",
                                      icon_left="trash-2")

                    ui.heading("On ui.icon_button", level=3)
                    with ui.hstack(gap="sm"):
                        with ui.tooltip("Save (Ctrl+S)"):
                            ui.icon_button("save", aria_label="Save")
                        with ui.tooltip("Delete"):
                            ui.icon_button("trash-2", color="error",
                                           aria_label="Delete")

                    ui.heading("On ui.avatar (presence detail)", level=3)
                    with ui.hstack():
                        with ui.tooltip("Ada Lovelace — online"):
                            ui.avatar(initials="AL", color="primary",
                                      status="online")

                    ui.heading("On ui.input (hint)", level=3)
                    ui.text(
                        "Useful for hint text without the visible "
                        "FormField helper text.",
                        color="muted", size="xs",
                    )
                    with ui.flex(classes="max-w-xs"):
                        with ui.tooltip(
                            "Format : +XX X XX XX XX XX",
                            position="bottom",
                        ):
                            ui.input(placeholder="Phone number",
                                     type="tel")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Tooltip activates on hover AND keyboard "
                        "focus so keyboard users see it too. The "
                        "panel is ``pointer-events-none`` so it "
                        "never intercepts clicks meant for the "
                        "trigger.",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        with ui.tooltip("Tab here to focus, "
                                        "Shift+Tab to leave"):
                            ui.button("Tab to focus me",
                                      icon_left="keyboard")

                    ui.heading('In a refreshing zone', level=3)
                    ui.text(
                        'The panel is teleported under <body>, so it does'
                            ' NOT live in the subtree the morph replaces. '
                            'Hover the button, click it (the zone refreshes),'
                            ' then leave it: the panel must disappear. If it '
                            'stayed, nothing could close it any more — '
                            'neither the mouse nor the keyboard.',
                        color="muted", size="xs",
                    )
                    tooltip_in_a_refreshed_zone()

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

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Tooltip's ``BINDABLE_PROPS = "
                        "('text',)`` contract. The panel text "
                        "swaps via ``bz-text`` on the bound state — "
                        "no network round-trip.",
                        color="muted", size="sm",
                    )
                    client = TooltipClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("text"):
                            ui.input(value=client.text,
                                     placeholder="Live hint")
                        with control("enabled (bound)"):
                            ui.switch(checked=client.enabled)

                    ui.divider()

                    with ui.flex(justify="center", align="center",
                                 classes="min-h-24"):
                        with ui.tooltip(client.text, position="top",
                                        color="info",
                                        enabled=client.enabled):
                            ui.button("Hover me", variant="outline")

                    ui.text(
                        "``enabled`` is re-read on every hover, not at "
                        "mount : flip the switch and the very next "
                        "hover obeys it. It shipped frozen for two "
                        "days because it was emitted as a ``bz-data`` "
                        "FIELD (evaluated once) instead of a method "
                        "body — and because nothing on this page ever "
                        "bound it.",
                        color="muted", size="xs",
                    )

                    ui.divider()

                    preview = ui.tooltip(client.text, color="info")
                    with preview:
                        ui.button("Hover", variant="outline")
                    emitted_html_block(
                        "Emitted HTML — &lt;span bz-text&gt; on the "
                        "panel bound to "
                        "$bz.state.TooltipClient.default.text.",
                        serialize_html(preview),
                    )
