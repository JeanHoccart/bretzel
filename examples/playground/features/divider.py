"""``Divider`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``label`` is the reactive
surface exercised client-side.

Divider has three props (``orientation`` / ``label`` / ``color``), no
events. ``label`` is slot-shaped (str | Component | ClientBinding via
``adopt_slot``/``emit_text_slot``). The Server playground wires every
prop AND every universal escape hatch (``classes`` /
``id`` / ``aria-label`` / ``style`` / ``attrs`` / ``visible`` /
``tooltip``) to a control, and the emitted HTML refreshes live next to
the preview.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/divider"


ORIENTATIONS = ["horizontal", "vertical"]
COLORS = ["primary", "secondary", "success",
          "warning", "error", "info", "muted"]


class DividerPlayground(PageState):
    """Server playground state — one field per prop + per universal
    escape hatch + per universal modifier. Empty strings mean "don't
    pass the kwarg" so the component picks its own default."""

    orientation: str = field(default="horizontal")
    label:       str = field(default="")
    color:       str = field(default="muted")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class DividerClient(ClientState, persist="memory"):
    """Mirror of Divider's BINDABLE_PROPS = ('label',)."""

    label: str = field(default="OR")


def server_changed(state: DividerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted). The
    # ``deps=[DividerPlayground]`` on ``server_panel`` re-renders it.
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


def build_preview(state: DividerPlayground):
    kwargs: dict = {
        "orientation": state.orientation,
        "color": state.color,
    }
    if state.label:
        kwargs["label"] = state.label
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
    return ui.divider(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[DividerPlayground])
def server_panel() -> None:
    state = DividerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("orientation"):
            ui.select(value=state.orientation,
                      options=[(o, o) for o in ORIENTATIONS],
                      on_change=server_changed)
        with control("label"):
            ui.input(value=state.label, placeholder="OR",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c.title()) for c in COLORS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!my-8",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-divider",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Section break",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.5",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=divider\nrole=presentation",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Section divider",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    # ── Live preview ─────────────────────────────────────────────────
    # Wrap in content so the divider has something to separate. For
    # vertical, switch to hstack with explicit height on the wrapper
    # so the line has somewhere to grow.
    if state.orientation == "vertical":
        with ui.hstack(align="center", classes="min-h-16"):
            ui.text("Left")
            build_preview(state)
            ui.text("Right")
    else:
        with ui.vstack():
            ui.text("Above")
            build_preview(state)
            ui.text("Below")

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Divider", level=1)
            ui.text(
                "Horizontal or vertical separator with optional label. "
                "Quick visual reference below ; the real stress-testing "
                "lives in the Server playground card — every prop and "
                "every escape hatch is wired to a control, and the "
                "emitted HTML is shown live underneath the preview.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Orientation — horizontal (default)", level=3)
                    with ui.vstack():
                        ui.text("Section A")
                        ui.divider()
                        ui.text("Section B")

                    ui.heading("Orientation — vertical", level=3)
                    with ui.hstack(align="center", classes="min-h-12"):
                        ui.text("Left")
                        ui.divider(orientation="vertical")
                        ui.text("Right")

                    ui.heading("With label", level=3)
                    with ui.vstack():
                        ui.text("Section A")
                        ui.divider(label="OR")
                        ui.text("Section B")
                        ui.divider(label="Continue with email")
                        ui.text("Section C")

                    ui.heading("Colors", level=3)
                    with ui.vstack():
                        ui.divider(color="primary",   label="primary")
                        ui.divider(color="secondary", label="secondary")
                        ui.divider(color="success",   label="success")
                        ui.divider(color="warning",   label="warning")
                        ui.divider(color="error",     label="error")
                        ui.divider(color="info",      label="info")
                        ui.divider(color="muted",     label="muted")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``label`` is slot-shaped (``adopt_slot`` / "
                        "``emit_text_slot`` accept str | Component | "
                        "ClientBinding).",
                        color="muted", size="sm",
                    )

                    ui.heading("label=str (the common case)", level=3)
                    with ui.vstack():
                        ui.divider(label="OR")

                    ui.heading("label=Component", level=3)
                    with ui.vstack():
                        ui.divider(
                            label=ui.text("Section", weight="bold",
                                          color="primary"),
                        )

                    ui.text(
                        "label=ClientBinding is demonstrated in the "
                        "Client playground below.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        "Inputs that historically break components "
                        "elsewhere. Reproduce any of them live via the "
                        "Server playground below.",
                        color="muted", size="sm",
                    )

                    ui.heading("Empty label (omitted)", level=3)
                    ui.divider(label="")

                    ui.heading("Very long label (80 chars)", level=3)
                    ui.divider(label="A" * 80)

                    ui.heading("Emoji + multi-script", level=3)
                    ui.divider(label="Ship 🚀 — שלום — 中文")

                    ui.heading("HTML-special characters (XSS escape)", level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.divider(label="<script>alert(1)</script>")

                    ui.heading("Vertical with label", level=3)
                    with ui.hstack(align="center", classes="min-h-16"):
                        ui.text("Left")
                        ui.divider(orientation="vertical", label="VS")
                        ui.text("Right")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Divider nested inside other Bretzel "
                            "components.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Header", weight="bold")
                            ui.divider()
                            ui.text("Body copy here.", color="muted")
                            ui.divider(label="actions")
                            with ui.hstack():
                                ui.button("Cancel", variant="ghost")
                                ui.button("Save",   color="primary")

                    ui.heading("Between hstack cells", level=3)
                    with ui.hstack(align="center", classes="min-h-12"):
                        ui.text("Step 1")
                        ui.divider(orientation="vertical")
                        ui.text("Step 2")
                        ui.divider(orientation="vertical")
                        ui.text("Step 3")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Hover-explained section break"):
                        ui.divider(label="hover me")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Divider emits ``role=\"separator\"`` and "
                        "``aria-orientation`` automatically. Screen "
                        "readers announce it as a section break. "
                        "Customise the announcement via the "
                        "``aria-label`` control in the Server "
                        "playground below.",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        ui.text("Above the separator.")
                        ui.divider(label="announced section")
                        ui.text("Below the separator.")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "The real test bench. Every prop AND every "
                        "escape hatch is wired to a control ; the "
                        "preview and the emitted HTML both refresh on "
                        "every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "The input and Divider share one ClientState "
                        "field. Each keystroke updates the label through "
                        "bz-text without a server round-trip.",
                        color="muted", size="sm",
                    )
                    client = DividerClient()
                    with control("label"):
                        ui.input(value=client.label, placeholder="OR")

                    ui.divider()

                    with ui.vstack():
                        ui.text("Above")
                        ui.divider(label=client.label, color="primary")
                        ui.text("Below")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — the centre span carries bz-text "
                        "bound to $bz.state.DividerClient.default.label.",
                        serialize_html(
                            ui.divider(label=client.label, color="primary")
                        ),
                    )
