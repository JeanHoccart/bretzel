"""``Container`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — Container is a pure
layout clamp ; mutate via ``visible=`` / conditional render.

One prop : ``width`` (sm / md / lg / xl / 2xl / full). No events, no
slots beyond children.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/container"


WIDTHS = ["sm", "md", "lg", "xl", "2xl", "full"]


class ContainerPlayground(PageState):
    width:       str = field(default="lg")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: ContainerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[ContainerPlayground] on server_panel triggers the re-render.
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


def build_preview(state: ContainerPlayground) -> dict:
    kwargs: dict = {"width": state.width}
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


@refreshable(deps=[ContainerPlayground])
def server_panel() -> None:
    state = ContainerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("width"):
            ui.select(value=state.width,
                      options=[(w, w) for w in WIDTHS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!bg-muted/10",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-container",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Main column",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="border: 1px dashed red",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=container",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Main page column",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    # Wrap the preview Container in a thin outline Card so the clamp
    # is visible against the surrounding page.
    with ui.card(padding="none"):
        with ui.container(**build_preview(state)):
            ui.text(f"Container width={state.width}",
                    color="muted", weight="bold")
            ui.text("Body content here.", color="muted", size="sm")

    ui.divider()

    preview = ui.container(**build_preview(state))
    with preview:
        ui.text("Body", color="muted")
    emitted_html_block(
        "Emitted HTML (preview Container with a single text)",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Container", level=1)
            ui.text(
                "Centered max-width layout primitive. One prop "
                "(``width``) picks the clamp ; horizontal + vertical "
                "padding is baked into the root. Compose ``Container "
                "> VStack`` when a different spacing scale is needed. "
                "The Server playground card stress-tests every escape "
                "hatch ; the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Each container below is wrapped in a "
                        "padding-less Card so the max-width clamp "
                        "is visible against the page edge.",
                        color="muted", size="sm",
                    )

                    for w in WIDTHS:
                        ui.heading(f"width={w}", level=3)
                        with ui.card(padding="none"):
                            with ui.container(width=w):
                                ui.text(f"width={w} container",
                                        color="muted", size="sm")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual usage patterns.",
                            color="muted", size="sm")

                    ui.heading("Empty container (no children)", level=3)
                    ui.text(
                        "Renders the padded box but nothing inside. "
                        "Useful as a layout anchor while content is "
                        "loading.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="none"):
                        ui.container()

                    ui.heading("Nested containers (anti-pattern)",
                               level=3)
                    ui.text(
                        "Outer + inner both add the baked padding ; "
                        "you usually want one Container, then "
                        "VStack/Grid/Flex for spacing. Demonstrated "
                        "here for visibility.",
                        color="muted", size="xs",
                    )
                    with ui.container(width="md"):
                        with ui.container(width="sm"):
                            ui.text("Doubly clamped + doubly padded.",
                                    color="muted", size="sm")

                    ui.heading("Container as <section> via tag override",
                               level=3)
                    with ui.container(width="sm", tag="section"):
                        ui.text(
                            "Rendered as <section> — same layout, "
                            "different semantics.",
                            color="muted", size="sm",
                        )

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Typical usage shapes.",
                            color="muted", size="sm")

                    ui.heading("Container > VStack (most common)", level=3)
                    with ui.card(padding="none"):
                        with ui.container(width="md"):
                            with ui.vstack(gap="md"):
                                ui.heading("Section title", level=3)
                                ui.text("Body copy.", color="muted")
                                ui.button("Action", color="primary")

                    ui.heading("Container > Grid (responsive cards)",
                               level=3)
                    with ui.card(padding="none"):
                        with ui.container(width="lg"):
                            with ui.grid(cols={"base": 1, "sm": 2,
                                               "md": 3}, gap="md"):
                                for i in range(1, 4):
                                    with ui.card(hoverable=True):
                                        ui.heading(f"Card {i}",
                                                   level=4)
                                        ui.text("Body",
                                                color="muted", size="sm")

                    ui.heading("Container > Hstack (top bar)", level=3)
                    with ui.card(padding="none"):
                        with ui.container(width="xl"):
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.heading("Bretzel", level=3)
                                with ui.hstack(gap="md"):
                                    ui.link("Docs",   href="#")
                                    ui.link("Github", href="#",
                                            external=True)
                                    ui.button("Sign in",
                                              variant="outline",
                                              size="sm")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Container is a plain ``<div>`` by default — "
                        "no implicit landmark role. Use the ``tag=`` "
                        "override (``ui.container(tag=\"main\")`` / "
                        "``tag=\"section\"`` / etc.) to expose proper "
                        "landmark semantics to screen readers.",
                        color="muted", size="sm",
                    )
                    with ui.card(padding="none"):
                        with ui.container(width="sm", tag="main",
                                          aria_label="Main content"):
                            ui.text(
                                "Rendered as <main aria-label='Main "
                                "content'>",
                                color="muted", size="sm",
                            )

            # ── Card 5 — Server playground ──────────────────────────
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
