"""``VStack`` / ``HStack`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` (inherited from Flex) so
no Client cards, no events.

VStack bakes ``direction=\"col\"`` in ; HStack bakes ``direction=\"row\"``
in — the axis is fixed (there is no bare ``Stack`` and no ``direction``
prop ; drop to ``ui.flex`` for a runtime-chosen axis). Two exposed axes
(``gap`` / ``align``). The Server playground exercises both shortcuts
via a ``shortcut=`` toggle.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/stack"


SHORTCUTS = ["vstack", "hstack"]
GAPS      = ["none", "xs", "sm", "md", "lg", "xl"]
V_ALIGNS  = ["start", "center", "end", "stretch"]
H_ALIGNS  = ["start", "center", "end", "stretch", "baseline"]


def swatch(label: str) -> None:
    with ui.card(padding="sm"):
        ui.text(label)


class StackPlayground(PageState):
    shortcut:    str = field(default="vstack")
    gap:         str = field(default="md")
    align:       str = field(default="stretch")
    item_count:  int = field(default=3)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: StackPlayground) -> None:
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


def shortcut_fn(name: str):
    return {"vstack": ui.vstack, "hstack": ui.hstack}[name]


def build_preview(state: StackPlayground) -> dict:
    kwargs: dict = {"gap": state.gap, "align": state.align}
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


@refreshable(deps=[StackPlayground])
def server_panel() -> None:
    state = StackPlayground()
    valid_aligns = H_ALIGNS if state.shortcut == "hstack" else V_ALIGNS

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("shortcut"):
            ui.select(value=state.shortcut,
                      options=[(s, s) for s in SHORTCUTS],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.align,
                      options=[(a, a) for a in valid_aligns],
                      on_change=server_changed)
        with control("item_count (preview only)"):
            ui.number_input(value=state.item_count,
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!min-h-32",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-stack",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Item list",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="min-height: 80px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=stack",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Item list",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    shortcut = shortcut_fn(state.shortcut)
    kwargs = build_preview(state)
    with ui.card(padding="sm"):
        with shortcut(**kwargs):
            for i in range(int(state.item_count or 0)):
                swatch(f"Item {i + 1}")

    ui.divider()

    preview = shortcut(**kwargs)
    with preview:
        for i in range(int(state.item_count or 0)):
            swatch(f"Item {i + 1}")
    emitted_html_block(
        f"Emitted HTML ({state.shortcut} + sample children)",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("VStack · HStack", level=1)
            ui.text(
                "Direction-baked ``Flex`` shortcuts. ``VStack`` is "
                "vertical (``direction=\"col\"``) ; ``HStack`` flips to "
                "``direction=\"row\"`` and defaults ``align=\"center\"`` "
                "(rows usually want vertical-centred children). The axis "
                "is fixed per shortcut — drop to ``ui.flex`` for a "
                "runtime-chosen direction. The Server playground card "
                "lets you switch between the two shortcuts live.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every shortcut.",
                            color="muted", size="sm")

                    ui.heading("VStack (vertical, default)", level=3)
                    with ui.card(padding="sm"):
                        with ui.vstack():
                            swatch("first")
                            swatch("second")
                            swatch("third")

                    ui.heading("HStack (horizontal, align=center)",
                               level=3)
                    with ui.card(padding="sm"):
                        with ui.hstack():
                            swatch("first")
                            swatch("second")
                            swatch("third")

                    ui.heading("Gap (VStack)", level=3)
                    with ui.vstack():
                        for g in GAPS:
                            ui.text(f"gap={g}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.vstack(gap=g):
                                    swatch("A")
                                    swatch("B")
                                    swatch("C")

                    ui.heading("Gap (HStack)", level=3)
                    with ui.vstack():
                        for g in GAPS:
                            ui.text(f"gap={g}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.hstack(gap=g):
                                    swatch("A")
                                    swatch("B")
                                    swatch("C")

                    ui.heading("Align (VStack — cross-axis horizontal)",
                               level=3)
                    with ui.vstack():
                        for a in V_ALIGNS:
                            ui.text(f"align={a}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.vstack(align=a):
                                    swatch("Short")
                                    swatch("Medium label")
                                    swatch("A wider label here")

                    ui.heading("Align (HStack — cross-axis vertical)",
                               level=3)
                    with ui.vstack():
                        for a in H_ALIGNS:
                            ui.text(f"align={a}",
                                    color="muted", size="sm")
                            with ui.card(padding="sm"):
                                with ui.hstack(align=a):
                                    swatch("Short")
                                    with ui.card(padding="md"):
                                        ui.text("Medium")
                                    with ui.card(padding="lg"):
                                        ui.text("Tall")

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual usage patterns.",
                            color="muted", size="sm")

                    ui.heading("Empty stack (no children)", level=3)
                    with ui.card(padding="sm"):
                        ui.vstack()

                    ui.heading("Single child", level=3)
                    with ui.card(padding="sm"):
                        with ui.vstack():
                            swatch("Alone")

                    ui.heading("Runtime-chosen axis → ui.flex", level=3)
                    ui.text(
                        "VStack / HStack bake their axis, so for a "
                        "direction decided at runtime drop to ``ui.flex`` "
                        "(the escape hatch that still exposes "
                        "``direction`` / ``justify`` / ``wrap``).",
                        color="muted", size="xs",
                    )
                    with ui.card(padding="sm"):
                        with ui.flex(direction="row", gap="md"):
                            swatch("flex row 1")
                            swatch("flex row 2")
                            swatch("flex row 3")

                    ui.heading("Deeply nested vstacks", level=3)
                    with ui.card(padding="sm"):
                        with ui.vstack(gap="sm"):
                            with ui.vstack(gap="xs"):
                                swatch("Outer / inner A1")
                                swatch("Outer / inner A2")
                            with ui.vstack(gap="xs"):
                                swatch("Outer / inner B1")
                                swatch("Outer / inner B2")

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Stack patterns you'll use every day.",
                            color="muted", size="sm")

                    ui.heading("Card content (VStack inside Card)",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Title", level=3)
                            ui.text("Body copy.", color="muted")
                            ui.button("Action", color="primary")

                    ui.heading("Toolbar (HStack with gap)", level=3)
                    with ui.card(padding="sm"):
                        with ui.hstack(gap="sm"):
                            ui.button("Save",   icon_left="save")
                            ui.button("Open",   icon_left="folder-open",
                                      variant="outline")
                            ui.button("Delete", icon_left="trash-2",
                                      variant="ghost", color="error")

                    ui.heading("Label + value pairs (HStack)", level=3)
                    with ui.vstack(gap="sm"):
                        for label, val in (
                            ("Name",   "Ada Lovelace"),
                            ("Email",  "ada@example.com"),
                            ("Status", "Active"),
                        ):
                            with ui.hstack(justify="between",
                                           align="center"):
                                ui.text(label, color="muted")
                                ui.text(val, weight="bold")

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Stack subclasses inherit Flex's plain "
                        "``<div>`` semantics — no implicit landmark. "
                        "Override with ``tag=`` (e.g. "
                        "``ui.vstack(tag=\"nav\")``) when the stack "
                        "represents a navigation list, toolbar, or "
                        "ordered group. Keyboard test : Tab through "
                        "the toolbar below — the stack itself is "
                        "inert, only its focusable children (the "
                        "buttons) receive focus, in DOM order.",
                        color="muted", size="sm",
                    )
                    with ui.card(padding="sm"):
                        with ui.hstack(tag="nav", gap="md",
                                       aria_label="Toolbar"):
                            ui.button("Save",  icon_left="save")
                            ui.button("Print", icon_left="printer",
                                      variant="outline")

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Switch between ``vstack`` / ``hstack`` live and "
                        "tune the gap / align / item-count knobs. The "
                        "preview AND the emitted HTML both refresh on "
                        "every change.",
                        color="muted", size="sm",
                    )
                    server_panel()
