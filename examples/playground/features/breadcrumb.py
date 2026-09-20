"""``Breadcrumb`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` so no Client cards ;
``EVENTS = ()`` so no Server events card. Pure structural component
— items list is server-rendered.

Four props : ``items`` / ``separator`` / ``color`` / ``size``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/breadcrumb"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["current", "primary", "secondary", "success", "warning",
          "error", "info", "muted"]


TRAIL = [
    {"label": "Home",       "href": "/"},
    {"label": "Components", "href": "/"},
    {"label": "Navigation", "href": "/"},
    {"label": "Breadcrumb"},  # current page, no href
]


class BreadcrumbPlayground(PageState):
    separator:   str = field(default="chevron-right")
    color:       str = field(default="primary")
    size:        str = field(default="md")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: BreadcrumbPlayground) -> None:
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


def build_preview(state: BreadcrumbPlayground):
    kwargs: dict = {
        "items": TRAIL,
        "separator": state.separator,
        "color": state.color,
        "size": state.size,
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
    return ui.breadcrumb(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[BreadcrumbPlayground])
def server_panel() -> None:
    state = BreadcrumbPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("separator (icon name or literal text)"):
            ui.input(value=state.separator,
                     placeholder="chevron-right / slash / /",
                     on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!gap-3",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-breadcrumb",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="You are here",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="font-style: italic",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=breadcrumb",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Page trail",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Breadcrumb", level=1)
            ui.text(
                "Page-location trail — flat row of links separated "
                "by a marker (chevron by default). Last item is the "
                "current page, rendered as plain text with "
                "``aria-current=\"page\"``. The Server playground "
                "card stress-tests every prop ; the emitted HTML "
                "is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic", level=3)
                    ui.breadcrumb(items=TRAIL)

                    ui.heading("Item shape — tuple / string / dict",
                               level=3)
                    with ui.vstack():
                        ui.text("List of (label, href) tuples",
                                color="muted", size="xs")
                        ui.breadcrumb(items=[
                            ("Home", "/"),
                            ("Docs", "/docs"),
                            ("API",  None),
                        ])
                        ui.text("List of bare strings (no links)",
                                color="muted", size="xs")
                        ui.breadcrumb(items=["Home", "Docs", "API"])
                        ui.text("List of dicts",
                                color="muted", size="xs")
                        ui.breadcrumb(items=TRAIL)

                    ui.heading("Enfants — icone, lien, contenu riche",
                               level=3)
                    with ui.vstack():
                        ui.text('items= stays the shorthand for the text case; '
                            'the children give the same surface as ui.tab / '
                            'ui.sidebar_item.',
                                color="muted", size="xs")
                        with ui.breadcrumb():
                            ui.breadcrumb_item("Home", icon="house", href="/")
                            ui.breadcrumb_item("Docs", icon="book",
                                               href="/docs")
                            ui.breadcrumb_item("API")
                        ui.text('label is a slot: it accepts a Component when '
                            'text is not enough. And the last segment '
                            'receives aria-current on its own.',
                                color="muted", size="xs")
                        with ui.breadcrumb():
                            ui.breadcrumb_item("Projets", href="/p")
                            ui.breadcrumb_item(
                                ui.badge(label="Tracker", color="primary")
                            )
                        ui.text('items= expresses the icon too, through the dict '
                            'form — the two levels stay equivalent.',
                                color="muted", size="xs")
                        ui.breadcrumb(items=[
                            {"label": "Home", "href": "/", "icon": "house"},
                            {"label": "Reglages", "icon": "settings"},
                        ])

                    ui.heading("Separator", level=3)
                    with ui.vstack():
                        for sep in ("chevron-right", "slash", "/",
                                    ">", "dot", "•"):
                            ui.text(f"separator={sep!r}",
                                    color="muted", size="xs")
                            ui.breadcrumb(items=TRAIL, separator=sep)

                    ui.heading("Sizes", level=3)
                    with ui.vstack():
                        for s in SIZES:
                            ui.text(f"size={s}",
                                    color="muted", size="xs")
                            ui.breadcrumb(items=TRAIL, size=s)

                    ui.heading("Colors", level=3)
                    with ui.vstack():
                        for c in COLORS:
                            ui.breadcrumb(items=TRAIL, color=c)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``separator`` is slot-shaped : str (icon "
                        "name or literal text, shown throughout — "
                        "see Reference) or Component.",
                        color="muted", size="sm",
                    )

                    ui.heading("separator=Component", level=3)
                    with ui.vstack():
                        ui.breadcrumb(
                            items=TRAIL,
                            separator=ui.icon("arrow-right",
                                              color="primary", size="xs"),
                        )

            # ── Card 3 — Edge cases ───────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs.",
                            color="muted", size="sm")

                    ui.heading("Single item", level=3)
                    ui.breadcrumb(items=[{"label": "Home only"}])

                    ui.heading("Empty list (renders nothing)",
                               level=3)
                    ui.breadcrumb(items=[])

                    ui.heading("Many items (10)", level=3)
                    ui.breadcrumb(items=[
                        {"label": f"L{i}", "href": "/"}
                        for i in range(1, 10)
                    ] + [{"label": "Current"}])

                    ui.heading("Very long labels", level=3)
                    ui.breadcrumb(items=[
                        {"label": "A really long top-level "
                                  "section name", "href": "/"},
                        {"label": "Another wordy intermediate "
                                  "section", "href": "/"},
                        {"label": "Current page also has a long "
                                  "title"},
                    ])

                    ui.heading("Emoji + multi-script labels", level=3)
                    ui.breadcrumb(items=[
                        {"label": "🏠 Home",    "href": "/"},
                        {"label": "שלום",      "href": "/"},
                        {"label": "中文 here"},
                    ])

                    ui.heading("HTML-special label (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the labels.",
                        color="muted", size="xs",
                    )
                    ui.breadcrumb(items=[
                        {"label": "<script>alert(1)</script>",
                         "href": "/"},
                        {"label": "Safe"},
                    ])

                    ui.heading("All items have href (last is "
                               "still current)", level=3)
                    ui.text(
                        "The last item is always treated as the "
                        "current page, regardless of href. The href "
                        "is ignored on render.",
                        color="muted", size="xs",
                    )
                    ui.breadcrumb(items=[
                        {"label": "A", "href": "/"},
                        {"label": "B", "href": "/"},
                        {"label": "C", "href": "/"},
                    ])

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Breadcrumb in common contexts.",
                            color="muted", size="sm")

                    ui.heading("Above a page heading", level=3)
                    with ui.vstack():
                        ui.breadcrumb(items=TRAIL)
                        ui.heading("Breadcrumb component", level=1)
                        ui.text("Page body content here.",
                                color="muted")

                    ui.heading("Inside ui.card (header strip)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.breadcrumb(items=[
                                {"label": "Projects", "href": "/"},
                                {"label": "Aurora"},
                            ], size="sm")
                            ui.heading("Aurora", level=3)
                            ui.text("Card body.",
                                    color="muted")

                    ui.heading("With trailing actions (hstack)",
                               level=3)
                    with ui.hstack(justify="between", align="center"):
                        ui.breadcrumb(items=TRAIL)
                        ui.button("Edit", icon_left="pencil",
                                  variant="outline", size="sm")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Root emits ``<nav aria-label="
                        "\"breadcrumb\">``. The last item carries "
                        "``aria-current=\"page\"`` so screen "
                        "readers announce the user's current "
                        "location. Override the default aria-label "
                        "via the ``aria-label`` control in the "
                        "Server playground.",
                        color="muted", size="sm",
                    )
                    ui.breadcrumb(items=TRAIL,
                                  aria_label="You are here")

                    ui.heading("Keyboard test", level=3)
                    ui.text(
                        "Items with an ``href`` are native ``<a>`` "
                        "links — Tab moves through them in order, "
                        "Enter activates. The current-page item has "
                        "no ``href`` (it's a ``<span>``) and is "
                        "correctly skipped by Tab.",
                        color="muted", size="sm",
                    )
                    ui.breadcrumb(items=[
                        ("Home", "/"),
                        ("Docs", "/"),
                        "Current page",
                    ])

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every prop AND every escape hatch is "
                        "wired to a control ; the preview AND the "
                        "emitted HTML both refresh on every "
                        "change. The ``items`` list itself is "
                        "kept fixed — see the Reference card for "
                        "shape demos.",
                        color="muted", size="sm",
                    )
                    server_panel()
