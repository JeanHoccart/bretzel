"""``Icon`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"name\",)`` — only the icon name is bindable ; size / color / set /
style stay design-time.

Five props : ``name`` (positional, str | ClientBinding), ``size``,
``color``, ``set``, ``style``. No events.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/icon"


SIZES   = ["xs", "sm", "md", "lg", "xl", "2xl"]
COLORS  = ["primary", "secondary", "success", "warning",
           "error", "info", "muted", "current"]
SETS    = ["lucide", "phosphor", "material-symbols", "tabler",
           "ph", "heroicons"]
STYLES  = ["", "regular", "bold", "duotone", "fill", "light"]
SAMPLES = ["save", "trash-2", "user", "settings", "heart",
           "star", "rocket", "info", "alert-triangle"]


class IconPlayground(PageState):
    name:        str = field(default="rocket")
    size:        str = field(default="md")
    color:       str = field(default="current")
    set:         str = field(default="")
    style:       str = field(default="")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    extra_style: str = field(default="")  # avoid collision with ``style``
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class IconClient(ClientState, persist="memory"):
    """Mirror of Icon's BINDABLE_PROPS = ('name',)."""

    name: str = field(default="rocket")


def server_changed(state: IconPlayground) -> None:
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


def build_preview(state: IconPlayground):
    kwargs: dict = {
        "size": state.size,
        "color": state.color,
    }
    if state.set:
        kwargs["set"] = state.set
    if state.style:
        kwargs["style"] = state.style
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.extra_style:
        # Icon already exposes ``style=`` as the Iconify *style suffix*
        # ; the inline CSS style goes through ``attrs`` instead.
        merged = dict(kwargs.get("attrs") or {})
        existing = merged.get("style", "")
        merged["style"] = (
            f"{existing}; " if existing else ""
        ) + state.extra_style
        kwargs["attrs"] = merged
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.icon(state.name, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[IconPlayground])
def server_panel() -> None:
    state = IconPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("name"):
            ui.input(value=state.name, placeholder="rocket",
                     on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("set (empty = theme default 'lucide')"):
            ui.select(value=state.set,
                      options=[("", "default")]
                              + [(s, s) for s in SETS],
                      on_change=server_changed)
        with control("style (phosphor / tabler suffix)"):
            ui.select(value=state.style,
                      options=[(s, s or "(none)") for s in STYLES],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!opacity-70",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-icon",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Rocket icon",
                     on_change=server_changed)
        with control("inline style (via attrs)"):
            ui.input(value=state.extra_style,
                     placeholder="transform: rotate(15deg)",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=icon",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Launch",
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
            ui.heading("Icon", level=1)
            ui.text(
                "Inline icon via the Iconify web component. Names "
                "without a prefix resolve against the theme's default "
                "set (``lucide``) ; ``set:icon`` syntax overrides "
                "per-call. The Server playground card stress-tests "
                "every prop ; the emitted HTML is shown live "
                "underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Names (default set 'lucide')", level=3)
                    with ui.hstack(gap="lg"):
                        for n in SAMPLES:
                            ui.icon(n)

                    ui.heading("Sizes", level=3)
                    with ui.hstack(align="end"):
                        for s in SIZES:
                            ui.icon("smile", size=s)

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS[:-1]:  # drop 'current' — context
                            ui.icon("circle", color=c)

                    ui.heading("Set override (same name, 3 sets)", level=3)
                    with ui.hstack(gap="lg"):
                        ui.icon("heart")  # default lucide
                        ui.icon("heart", set="phosphor")
                        ui.icon("heart", set="material-symbols")

                    ui.heading("Style suffix (phosphor)", level=3)
                    with ui.hstack(gap="lg"):
                        ui.icon("heart", set="phosphor")
                        ui.icon("heart", set="phosphor", icon_style="bold")
                        ui.icon("heart", set="phosphor", icon_style="duotone")
                        ui.icon("heart", set="phosphor", icon_style="fill")

                    ui.heading("Prefixed name passes through verbatim",
                               level=3)
                    with ui.hstack(gap="lg"):
                        ui.icon("lucide:star")
                        ui.icon("phosphor:moon")
                        ui.icon("material-symbols:bolt")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``name`` is the positional slot. Accepts str "
                        "(SSR resolves the set + style suffix) or "
                        "ClientBinding (the runtime + ``$bz._resolveIcon`` "
                        "mirror the same resolution client-side).",
                        color="muted", size="sm",
                    )

                    ui.heading("name=str", level=3)
                    ui.icon("rocket", size="xl", color="primary")

                    ui.text(
                        "name=ClientBinding — see Client playground",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Bind to a ClientState string ; both a static "
                        "``icon=`` (SSR fallback) and a ``:icon=`` "
                        "the runtime directive are emitted, so the glyph "
                        "appears immediately even before the runtime boots.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and graceful failure shapes.",
                            color="muted", size="sm")

                    ui.heading("Invalid name (renders empty / fallback)",
                               level=3)
                    ui.text(
                        "Iconify shows nothing for an unknown icon ; "
                        "the framework still emits the wrapper so "
                        "layout doesn't shift.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="lg"):
                        ui.icon("this-icon-does-not-exist")
                        ui.icon("nope:also-not-real")

                    ui.heading("Empty name", level=3)
                    ui.icon("")

                    ui.heading("Very large via size + classes", level=3)
                    with ui.hstack(align="center"):
                        ui.icon("rocket", size="2xl",
                                classes="!text-6xl")

                    ui.heading("Inherits ``text-current`` color",
                               level=3)
                    ui.text(
                        "``color=\"current\"`` lets the icon inherit "
                        "the parent's text colour — pair it with a "
                        "coloured parent rather than a duplicate "
                        "``color=`` prop.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="lg"):
                        with ui.flex(classes="text-success"):
                            ui.icon("check", color="current")
                        with ui.flex(classes="text-error"):
                            ui.icon("x", color="current")
                        with ui.flex(classes="text-primary"):
                            ui.icon("rocket", color="current")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Icon nested inside actions / overlays / "
                            "headings.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.button (icon_left / icon_right)",
                               level=3)
                    with ui.hstack():
                        ui.button("Save",  icon_left="save")
                        ui.button("Next",  icon_right="arrow-right")
                        ui.button("Heart", icon_left="heart",
                                  variant="outline", color="error")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.hstack():
                        with ui.tooltip("Search"):
                            ui.icon("search", size="lg")
                        with ui.tooltip("Settings"):
                            ui.icon("settings", size="lg")

                    ui.heading("Inside ui.heading (as content slot)",
                               level=3)
                    ui.heading(ui.icon("flag", size="lg", color="primary"),
                               level=3)

                    ui.heading("Inside ui.text (decorative inline)",
                               level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon("info", color="info")
                        ui.text("Some informational copy.",
                                color="info")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Standalone icons should carry an "
                        "``aria-label`` so screen readers announce "
                        "what they represent. Decorative icons "
                        "(beside a text label that says the same "
                        "thing) should be hidden via "
                        "``attrs={\"aria-hidden\": \"true\"}`` to "
                        "avoid duplicate announcements.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="lg"):
                        ui.icon("info", size="lg", aria_label="Information")
                        ui.icon("alert-triangle", size="lg",
                                color="warning", aria_label="Warning")
                        ui.icon("check", size="lg", color="success",
                                attrs={"aria-hidden": "true"})

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
                        "Mirror of Icon's ``BINDABLE_PROPS = "
                        "('name',)`` contract. the runtime + "
                        "``$bz._resolveIcon`` swap the icon name "
                        "without a network round-trip. Both a static "
                        "``icon=`` (SSR fallback) and a ``:icon=`` "
                        "the runtime directive are emitted so the glyph "
                        "appears immediately, then reactively updates.",
                        color="muted", size="sm",
                    )
                    client = IconClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("name (try save / heart / rocket / star)"):
                            ui.input(value=client.name,
                                     placeholder="rocket")

                    ui.divider()

                    with ui.flex(justify="center", align="center",
                                 classes="min-h-16"):
                        ui.icon(client.name, size="2xl", color="primary")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;iconify-icon&gt; with both "
                        "a static icon=… (SSR fallback) and a "
                        ":icon=$bz._resolveIcon(...) the runtime directive.",
                        serialize_html(
                            ui.icon(client.name, size="2xl",
                                    color="primary")
                        ),
                    )
