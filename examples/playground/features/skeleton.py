"""``Skeleton`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — Skeleton is a pure
placeholder ; toggle visibility from the parent via ``visible=``
when the data lands.

Four props (``variant`` / ``width`` / ``height`` / ``animated``), no
events, no slots.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/skeleton"


VARIANTS = ["text", "circle", "rectangle"]


class SkeletonPlayground(PageState):
    variant:     str = field(default="rectangle")
    width:       str = field(default="")     # any CSS unit
    height:      str = field(default="")
    animated:    bool = field(default=True)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: SkeletonPlayground) -> None:
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


def build_preview(state: SkeletonPlayground):
    kwargs: dict = {
        "variant": state.variant,
        "animated": state.animated,
    }
    if state.width:
        kwargs["width"] = state.width
    if state.height:
        kwargs["height"] = state.height
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
    return ui.skeleton(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[SkeletonPlayground])
def server_panel() -> None:
    state = SkeletonPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("width"):
            ui.input(value=state.width, placeholder="200px / 50%",
                     on_change=server_changed)
        with control("height"):
            ui.input(value=state.height, placeholder="1rem / 80px",
                     on_change=server_changed)
        with control("animated"):
            ui.switch(checked=state.animated, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-2xl",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-skeleton",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Loading content",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="opacity: 0.7",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=skeleton",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Loading…",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center", classes="min-h-16"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Skeleton", level=1)
            ui.text(
                "Loading-placeholder block. Three variants : "
                "``text`` (thin line), ``circle`` (avatar slot), "
                "``rectangle`` (everything else). The Server "
                "playground card exercises every prop ; the emitted "
                "HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every variant + animation.",
                            color="muted", size="sm")

                    ui.heading("Variants", level=3)
                    with ui.hstack(align="center"):
                        ui.skeleton(variant="text",      width="120px")
                        ui.skeleton(variant="circle",    width="48px",
                                    height="48px")
                        ui.skeleton(variant="rectangle", width="120px",
                                    height="80px")

                    ui.heading("Text — paragraph mock", level=3)
                    ui.text(
                        "Stack several with varying widths to mimic "
                        "paragraph lines.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm"):
                        ui.skeleton(variant="text", width="90%")
                        ui.skeleton(variant="text", width="85%")
                        ui.skeleton(variant="text", width="60%")

                    ui.heading("Rectangle — sizes", level=3)
                    with ui.hstack(align="center"):
                        ui.skeleton(width="80px",  height="40px")
                        ui.skeleton(width="120px", height="60px")
                        ui.skeleton(width="160px", height="80px")
                        ui.skeleton(width="200px", height="100px")

                    ui.heading("Animated vs static", level=3)
                    with ui.hstack(align="center"):
                        ui.skeleton(width="160px", height="40px",
                                    animated=True)
                        ui.skeleton(width="160px", height="40px",
                                    animated=False)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual sizing inputs and exotic units.",
                            color="muted", size="sm")

                    ui.heading("100% width inside a constrained parent",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.skeleton(variant="text",      width="100%")
                            ui.skeleton(variant="rectangle", width="100%",
                                        height="80px")

                    ui.heading("Pixel / rem / percent mix", level=3)
                    with ui.hstack(align="center"):
                        ui.skeleton(width="200px", height="2rem")
                        ui.skeleton(width="50%",   height="2rem")
                        ui.skeleton(width="10ch",  height="2rem")

                    ui.heading("Circle without explicit size (collapses)",
                               level=3)
                    ui.text(
                        "Without ``width=`` / ``height=`` the circle has "
                        "no intrinsic size — almost invisible. Always "
                        "set both for circles.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(align="center"):
                        ui.skeleton(variant="circle")

                    ui.heading("Static (animated=False) for screenshots",
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.skeleton(variant="text",      width="40%",
                                    animated=False)
                        ui.skeleton(variant="rectangle", width="60%",
                                    height="40px", animated=False)

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Skeleton is most effective when stacked to "
                            "match the post-load layout.",
                            color="muted", size="sm")

                    ui.heading("Avatar + two text lines (typical row)",
                               level=3)
                    with ui.hstack(align="center", gap="md"):
                        ui.skeleton(variant="circle", width="48px",
                                    height="48px")
                        with ui.vstack(gap="sm"):
                            ui.skeleton(variant="text", width="160px")
                            ui.skeleton(variant="text", width="100px")

                    ui.heading("Inside ui.card (whole-card placeholder)",
                               level=3)
                    with ui.card():
                        with ui.vstack(gap="md"):
                            with ui.hstack(align="center", gap="md"):
                                ui.skeleton(variant="circle", width="40px",
                                            height="40px")
                                ui.skeleton(variant="text",   width="150px")
                            ui.skeleton(variant="rectangle", width="100%",
                                        height="100px")
                            with ui.hstack(gap="sm"):
                                ui.skeleton(variant="rectangle",
                                            width="80px", height="32px")
                                ui.skeleton(variant="rectangle",
                                            width="80px", height="32px")

                    ui.heading("Stand-in for a Button while idle",
                               level=3)
                    with ui.hstack():
                        ui.skeleton(variant="rectangle", width="120px",
                                    height="40px",
                                    classes="!rounded-md")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Skeleton emits ``aria-hidden=\"true\"`` so "
                        "screen readers skip the placeholder entirely "
                        "and reach the real content (or the loading "
                        "announcement) once it arrives. Override the "
                        "ARIA hint via the Server playground if your "
                        "use case needs the placeholder announced.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(align="center"):
                        ui.skeleton(width="200px", height="40px")
                        ui.skeleton(variant="circle", width="48px",
                                    height="48px")

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is wired to "
                        "a control ; the preview and the emitted HTML "
                        "both refresh on every change.",
                        color="muted", size="sm",
                    )
                    server_panel()
