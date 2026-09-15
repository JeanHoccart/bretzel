"""``Progress`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"value\", \"label\")`` — both the current value AND the label string
are bindable ; max / color / size / show_label / indeterminate stay
design-time.

Seven props : ``value``, ``max``, ``indeterminate``, ``color``,
``size``, ``show_label``, ``label``. No events.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/progress"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class ProgressPlayground(PageState):
    value:         float = field(default=42.0)
    max:           float = field(default=100.0)
    indeterminate: bool  = field(default=False)
    color:         str   = field(default="primary")
    size:          str   = field(default="md")
    show_label:    bool  = field(default=False)
    label:         str   = field(default="")
    # Escape hatches.
    classes:       str   = field(default="")
    custom_id:     str   = field(default="")
    aria_label:    str   = field(default="")
    style:         str   = field(default="")
    extra_attrs:   str   = field(default="")
    # Universal modifiers.
    visible:       str   = field(default="on")
    tooltip:       str   = field(default="")


class ProgressClient(ClientState, persist="memory"):
    """Mirror of Progress's BINDABLE_PROPS = ('value', 'label')."""

    value: float = field(default=42.0)
    label: str   = field(default="")


def server_changed(state: ProgressPlayground) -> None:
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


def build_preview(state: ProgressPlayground):
    kwargs: dict = {
        "max": state.max,
        "indeterminate": state.indeterminate,
        "color": state.color,
        "size": state.size,
        "show_label": state.show_label,
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
    return ui.progress(state.value, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[ProgressPlayground])
def server_panel() -> None:
    state = ProgressPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (0 → max)"):
            ui.number_input(value=state.value,
                     on_change=server_changed)
        with control("max"):
            ui.number_input(value=state.max,
                     on_change=server_changed)
        with control("indeterminate"):
            ui.switch(checked=state.indeterminate,
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("show_label"):
            ui.switch(checked=state.show_label,
                      on_change=server_changed)
        with control("label (overrides percentage)"):
            ui.input(value=state.label,
                     placeholder="Uploading…",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!h-2",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-progress",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Upload progress",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-width: 320px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=progress",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Sync in progress",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        with ui.vstack(classes="min-w-64"):
            build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Progress", level=1)
            ui.text(
                "Linear progress indicator. Determinate mode "
                "renders a fill based on ``value / max`` ; "
                "indeterminate mode runs a looping animation when "
                "the operation has no measurable progress. The "
                "Server playground card stress-tests every prop ; "
                "the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Values (0 → max=100)", level=3)
                    with ui.vstack():
                        for v in (0, 25, 50, 75, 100):
                            ui.progress(v)

                    ui.heading("Custom max", level=3)
                    with ui.vstack():
                        ui.progress(3,   max=10)
                        ui.progress(7,   max=10)
                        ui.progress(150, max=200)

                    ui.heading("Indeterminate", level=3)
                    ui.text("No value — animated stripe.",
                            color="muted", size="xs")
                    ui.progress(indeterminate=True)

                    ui.heading("Sizes", level=3)
                    with ui.vstack():
                        for s in SIZES:
                            ui.progress(60, size=s)

                    ui.heading("Colors", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.progress(60, color=c)

                    ui.heading("With percentage label", level=3)
                    ui.progress(40, show_label=True)

                    ui.heading("With custom label", level=3)
                    ui.progress(80, label="Uploading…")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Two reactive slots : ``value`` (positional, "
                        "drives the fill width) and ``label=`` "
                        "(overrides the auto-percentage text). Both "
                        "accept ClientBinding — see Client playground.",
                        color="muted", size="sm",
                    )

                    ui.heading("value=int — static fill", level=3)
                    ui.progress(60, show_label=True)

                    ui.heading("label=str — explicit text", level=3)
                    ui.progress(60, label="3 of 5 files")

                    ui.heading(
                        "value + label both ClientBinding — see "
                        "Client playground",
                        level=3,
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Out-of-range values + exotic combos.",
                            color="muted", size="sm")

                    ui.heading("Negative value (clamps to 0)", level=3)
                    ui.progress(-10, show_label=True)

                    ui.heading("Value beyond max (clamps to 100)",
                               level=3)
                    ui.progress(150, max=100, show_label=True)

                    ui.heading("Max smaller than value", level=3)
                    ui.progress(75, max=50, show_label=True)

                    ui.heading("Zero", level=3)
                    ui.progress(0, show_label=True)

                    ui.heading("Indeterminate with label (label kept)",
                               level=3)
                    ui.progress(indeterminate=True, label="Working…")

                    ui.heading("Very long custom label", level=3)
                    ui.progress(
                        50,
                        label="Uploading photos from the user's "
                              "camera roll to the cloud archive",
                    )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Progress inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card (typical upload row)",
                               level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.text("photos-archive.zip",
                                        weight="bold")
                                ui.text("42%", color="muted", size="sm")
                            ui.progress(42, color="primary")

                    ui.heading("Inside ui.dialog (modal upload)",
                               level=3)
                    ui.text(
                        "The dialog is closed by default ; trigger "
                        "is omitted here to keep the playground "
                        "static — the structural composition still "
                        "type-checks.",
                        color="muted", size="xs",
                    )
                    ui.progress(70, show_label=True, color="info")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.flex(classes="min-w-64"):
                        with ui.tooltip("Storage : 7.2 GB of 10 GB used"):
                            ui.progress(72, color="warning",
                                        show_label=True)

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Progress emits ``role=\"progressbar\"`` with "
                        "``aria-valuenow / aria-valuemin / "
                        "aria-valuemax``. Indeterminate mode drops "
                        "``aria-valuenow`` per the WAI-ARIA spec. Pair "
                        "with a meaningful ``aria-label`` (via the "
                        "Server playground) when the visible label "
                        "alone doesn't describe the operation.",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        ui.progress(42, show_label=True,
                                    aria_label="Upload progress")
                        ui.progress(indeterminate=True,
                                    aria_label="Loading recommendations")

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
                        "Mirror of Progress's ``BINDABLE_PROPS = "
                        "('value', 'label')`` contract. the runtime writes "
                        "the fill width via a clamped expression on "
                        "every state mutation, and rewrites the label "
                        "via ``bz-text`` — no network round-trip. The "
                        "max axis stays design-time.",
                        color="muted", size="sm",
                    )
                    client = ProgressClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("value (0–100)"):
                            ui.number_input(value=client.value)
                        with control("label (overrides percentage)"):
                            ui.input(value=client.label,
                                     placeholder="Uploading…")

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        with ui.vstack(classes="min-w-64"):
                            ui.progress(client.value,
                                        label=client.label,
                                        color="primary",
                                        show_label=True)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — ``:style`` clamps "
                        "value / max to [0, 100]% on the fill, and "
                        "``bz-text`` swaps the label. The static "
                        "``style=\"width: 0%\"`` is the SSR fallback "
                        "before the runtime boots.",
                        serialize_html(
                            ui.progress(client.value,
                                        label=client.label,
                                        color="primary",
                                        show_label=True)
                        ),
                    )
