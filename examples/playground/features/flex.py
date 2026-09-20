"""``Flex`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — Flex is pure layout ;
mutate via ``visible=`` / conditional render.

Five props : ``direction`` / ``align`` / ``justify`` / ``gap`` /
``wrap``. No events. The convenience subclasses ``VStack`` / ``HStack``
bake one direction in — they have their own page.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/flex"


DIRECTIONS = ["row", "row-reverse", "col", "col-reverse"]
ALIGNS     = ["start", "center", "end", "stretch", "baseline"]
JUSTIFIES  = ["start", "center", "end", "between", "around", "evenly"]
GAPS       = ["none", "xs", "sm", "md", "lg", "xl"]
#: ``""`` = the prop is not asked for — and it is the default, because
#: a stack asking for nothing emits none of these classes.
GROWS      = ["", "equal", "12rem", "16rem", "20rem"]


def swatch(label: str) -> None:
    """Small coloured tile that makes flex layout visible inside each
    demo. Inline-style; kept private so it doesn't leak into the
    public ui.* namespace."""
    with ui.card(padding="sm"):
        ui.text(label)


def bar_fields() -> None:
    """Two filter fields — the real shape where ``grow=`` counts.

    Tiles would show nothing: they have no width of their own. The case
    that produced the prop is a field, whose root carries ``w-full``.
    """
    with ui.form_field(label="Search"):
        ui.input(placeholder="Search name, email, company…",
                 icon_left="search")
    with ui.form_field(label="Status"):
        ui.select(options=[("all", "All statuses"), ("live", "Live")],
                  value="all")


class FlexPlayground(PageState):
    direction:   str  = field(default="row")
    align:       str  = field(default="stretch")
    justify:     str  = field(default="start")
    gap:         str  = field(default="md")
    wrap:        bool = field(default=False)
    grow:        str  = field(default="")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


def server_changed(state: FlexPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    # deps=[FlexPlayground] re-renders server_panel automatically.
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


def build_preview(state: FlexPlayground) -> dict:
    kwargs: dict = {
        "direction": state.direction,
        "align": state.align,
        "justify": state.justify,
        "gap": state.gap,
        "wrap": state.wrap,
    }
    if state.grow:
        kwargs["grow"] = state.grow
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


@refreshable(deps=[FlexPlayground])
def server_panel() -> None:
    state = FlexPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
                      on_change=server_changed)
        with control("align (cross-axis)"):
            ui.select(value=state.align,
                      options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("justify (main-axis)"):
            ui.select(value=state.justify,
                      options=[(j, j) for j in JUSTIFIES],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("wrap"):
            ui.switch(checked=state.wrap, on_change=server_changed)
        with control("grow (the children's basis)"):
            ui.select(value=state.grow,
                      options=[(g, g or '— (not asked for)') for g in GROWS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!border !border-dashed",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-flex",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Toolbar",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="min-height: 80px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=flex",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Container",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.card(padding="sm"):
        with ui.flex(**build_preview(state)):
            for i in range(1, 5):
                swatch(f"Item {i}")

    ui.divider()

    preview = ui.flex(**build_preview(state))
    with preview:
        for i in range(1, 5):
            swatch(f"Item {i}")
    emitted_html_block(
        "Emitted HTML (Flex shell + 4 sample children)",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Flex", level=1)
            ui.text(
                "Generic CSS-flex container with the full axis API "
                "exposed. The convenience subclasses ``ui.vstack`` / "
                "``ui.hstack`` bake one direction in — check that page "
                "for the smaller surface. "
                "The Server playground card stress-tests every prop ; "
                "the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Direction", level=3)
                    with ui.vstack():
                        for d in DIRECTIONS:
                            ui.text(f"direction={d}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.flex(direction=d):
                                    swatch("A")
                                    swatch("B")
                                    swatch("C")

                    ui.heading("Align (cross-axis)", level=3)
                    with ui.vstack():
                        for a in ALIGNS:
                            ui.text(f"align={a}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.flex(align=a):
                                    swatch("Short")
                                    swatch("Medium")
                                    with ui.card(padding="lg"):
                                        ui.text("Tall")

                    ui.heading("Justify (main-axis)", level=3)
                    with ui.vstack():
                        for j in JUSTIFIES:
                            ui.text(f"justify={j}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.flex(justify=j):
                                    swatch("A")
                                    swatch("B")
                                    swatch("C")

                    ui.heading("Gap", level=3)
                    with ui.vstack():
                        for g in GAPS:
                            ui.text(f"gap={g}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.flex(gap=g):
                                    swatch("A")
                                    swatch("B")
                                    swatch("C")

                    ui.heading("Grow", level=3)
                    ui.text(
                        '``grow=`` says how the direct children share the'
                            ' main axis. The parent distributes it — no child'
                            ' needs to know, so it works with any component.',
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        # The control first: without it, one does not
                        # see what the prop changes. Two fields whose
                        # root carries ``w-full`` (every control's
                        # convention) cannot share a wrapping row — the
                        # bar becomes a STACK.
                        ui.text('with no grow= — the bar stacks up',
                                color="muted", size="sm")
                        with ui.card(padding="sm"):
                            with ui.flex(gap="md", align="end", wrap=True):
                                bar_fields()
                        for base in ("16rem", "12rem"):
                            ui.text(f'grow="{base}" — at least {base} per '
                                    f"field, then a line break",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.flex(gap="md", align="end",
                                             wrap=True, grow=base):
                                    bar_fields()
                        ui.text('grow=True — strictly equal shares, whatever the '
                            'content',
                                color="muted", size="sm")
                        with ui.card(padding="sm"):
                            with ui.flex(gap="md", align="end", grow=True):
                                bar_fields()

                    ui.heading("Wrap", level=3)
                    with ui.vstack():
                        ui.text("wrap=False (default)",
                                color="muted", size="sm")
                        with ui.card(padding="sm"):
                            with ui.flex():
                                for i in range(8):
                                    swatch(f"{i + 1}")
                        ui.text("wrap=True", color="muted", size="sm")
                        with ui.card(padding="sm"):
                            with ui.flex(wrap=True):
                                for i in range(8):
                                    swatch(f"{i + 1}")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual usage patterns.",
                            color="muted", size="sm")

                    ui.heading("Empty flex (no children)", level=3)
                    with ui.card(padding="sm"):
                        ui.flex()

                    ui.heading("One child only", level=3)
                    with ui.card(padding="sm"):
                        with ui.flex(justify="center"):
                            swatch("Alone")

                    ui.heading("Mixed gap + wrap on narrow container",
                               level=3)
                    with ui.flex(classes="max-w-xs"):
                        with ui.card(padding="sm"):
                            with ui.flex(gap="md", wrap=True):
                                for i in range(12):
                                    swatch(f"{i + 1}")

                    ui.heading("Column with baseline align", level=3)
                    ui.text(
                        "``baseline`` is a typographic align — it "
                        "only makes sense when children have an "
                        "intrinsic text baseline, mostly relevant on "
                        "rows.",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.flex(direction="col",
                                     align="baseline"):
                            ui.text("Big",   size="2xl")
                            ui.text("Small", size="sm")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Typical Flex shapes you'll reach for.",
                            color="muted", size="sm")

                    ui.heading("Header bar (justify=between)", level=3)
                    with ui.card(padding="sm"):
                        with ui.flex(justify="between", align="center"):
                            ui.heading("Title", level=3)
                            with ui.hstack(gap="sm"):
                                ui.button("Cancel", variant="ghost")
                                ui.button("Save",   color="primary")

                    ui.heading("Centered hero", level=3)
                    with ui.card(padding="lg"):
                        with ui.flex(direction="col", align="center",
                                     justify="center", gap="md",
                                     classes="min-h-32"):
                            ui.heading("Centered title", level=3)
                            ui.text("Subtitle copy.", color="muted")
                            ui.button("Get started", color="primary")

                    ui.heading("Sidebar + main (row, align=stretch)",
                               level=3)
                    with ui.card(padding="none"):
                        with ui.flex(align="stretch"):
                            with ui.card(color="muted", padding="md"):
                                with ui.vstack(gap="sm"):
                                    ui.text("Nav", weight="bold")
                                    ui.text("Item 1", color="muted")
                                    ui.text("Item 2", color="muted")
                            with ui.card(padding="lg"):
                                ui.text("Main content area",
                                        color="muted")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Flex is a plain ``<div>`` by default — no "
                        "implicit landmark role. Pair with the "
                        "``tag=`` override (e.g. ``ui.flex(tag="
                        "\"nav\")``) when the container has a "
                        "specific semantic role. ``aria-label`` and "
                        "``role`` flow through the universal "
                        "``attrs=`` / ``aria_label=`` kwargs.",
                        color="muted", size="sm",
                    )
                    with ui.card(padding="sm"):
                        with ui.flex(tag="nav", gap="md",
                                     aria_label="Primary navigation"):
                            ui.link("Home",    href="/")
                            ui.link("Docs",    href="/")
                            ui.link("Github",  href="/", external=True)

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
