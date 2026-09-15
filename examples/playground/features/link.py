"""``Link`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"label\", \"href\")`` — both the visible text AND the destination
are bindable ; variant / color / external / disabled stay
design-time.

Six props : ``text`` (positional label, str | ClientBinding), ``href``
(str | ClientBinding), ``variant``, ``color``, ``external`` (bool),
``disabled`` (bool). No events.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/link"


VARIANTS = ["hover", "underline", "text"]
COLORS   = ["primary", "secondary", "success", "warning",
            "error", "info", "muted"]


class LinkPlayground(PageState):
    label:       str  = field(default="Documentation")
    href:        str  = field(default="/button")
    variant:     str  = field(default="hover")
    color:       str  = field(default="primary")
    external:    bool = field(default=False)
    disabled:    bool = field(default=False)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class LinkClient(ClientState, persist="memory"):
    """Mirror of Link's BINDABLE_PROPS = ('label', 'href')."""

    label: str = field(default="Live destination")
    href:  str = field(default="/button")


def server_changed(state: LinkPlayground) -> None:
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


def build_preview(state: LinkPlayground):
    kwargs: dict = {
        "href": state.href,
        "variant": state.variant,
        "color": state.color,
        "external": state.external,
        "disabled": state.disabled,
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
    return ui.link(state.label, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[LinkPlayground])
def server_panel() -> None:
    state = LinkPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("label"):
            ui.input(value=state.label, placeholder="Documentation",
                     on_change=server_changed)
        with control("href"):
            ui.input(value=state.href, placeholder="/button",
                     on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("external"):
            ui.switch(checked=state.external, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!font-bold",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="docs-link",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Open documentation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="letter-spacing: 0.05em",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=link",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Read the docs",
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
            ui.heading("Link", level=1)
            ui.text(
                "Anchor with three visual variants (hover / underline "
                "/ text), every theme colour, plus the a11y-correct "
                "disabled state and the external-link safety pair "
                "(``target=_blank`` + ``rel=noopener noreferrer``). "
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

                    ui.heading("Variants", level=3)
                    with ui.hstack(gap="xl"):
                        ui.link("Hover (default)", href="#",
                                variant="hover")
                        ui.link("Underline", href="#", variant="underline")
                        ui.link("Text",      href="#", variant="text")

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True, gap="lg"):
                        for c in COLORS:
                            ui.link(c.title(), href="#", color=c)

                    ui.heading("External (new tab + rel=noopener)",
                               level=3)
                    with ui.hstack(gap="xl"):
                        ui.link("Internal page", href="/button")
                        ui.link("External resource",
                                href="https://example.com",
                                external=True)

                    ui.heading("Disabled", level=3)
                    with ui.hstack(gap="xl"):
                        ui.link("Active",   href="/")
                        ui.link("Disabled", href="/",  disabled=True)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``label`` is the positional slot. Accepts "
                        "str (literal), ClientBinding (live), or "
                        "child Components (nested icon + text via "
                        "``with`` block).",
                        color="muted", size="sm",
                    )

                    ui.heading("label=str", level=3)
                    ui.link("Plain text link", href="#")

                    ui.heading("Child Components (with block)", level=3)
                    with ui.link(href="#", color="primary"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("book-open")
                            ui.text("Read the docs")
                            ui.icon("arrow-right")

                    ui.text(
                        "label / href = ClientBinding — see Client "
                        "playground",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Both label AND href are in BINDABLE_PROPS — "
                        "you can rewrite either reactively without a "
                        "round-trip.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Edge inputs and exotic combinations.",
                            color="muted", size="sm")

                    ui.heading("Empty label", level=3)
                    ui.link("", href="#")

                    ui.heading("Very long label (80 chars)", level=3)
                    ui.link("A" * 80, href="#")

                    ui.heading("Emoji + multi-script", level=3)
                    ui.link("Ship 🚀 — שלום — 中文", href="#")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the label — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.link("<script>alert(1)</script>", href="#")

                    ui.heading("Disabled keeps the visual but neuters "
                               "the href", level=3)
                    ui.text(
                        "Inspect the emitted HTML in the Server "
                        "playground — disabled links drop ``href=`` "
                        "and add aria-disabled + tabindex=-1.",
                        color="muted", size="xs",
                    )
                    ui.link("Click me — but I won't navigate",
                            href="/button", disabled=True)

                    ui.heading("External + disabled (disabled wins)",
                               level=3)
                    ui.link("Locked external", href="https://example.com",
                            external=True, disabled=True)

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Link nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.text (inline reference)",
                               level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.text("See the ", color="muted")
                        ui.link("documentation", href="/button")
                        ui.text(" for details.", color="muted")

                    ui.heading("Inside ui.card (link list)", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Quick links", level=3)
                            with ui.vstack(gap="sm"):
                                ui.link("• Button reference",
                                        href="/button")
                                ui.link("• Input reference",
                                        href="/input")
                                ui.link("• Theme cookbook",
                                        href="https://bretzel.dev",
                                        external=True)

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Opens the Button reference"):
                        ui.link("Button reference", href="/button",
                                color="primary")

                    ui.heading("As ui.breadcrumb items", level=3)
                    ui.breadcrumb([
                        {"label": "Home",       "href": "/"},
                        {"label": "Components", "href": "/"},
                        {"label": "Link"},  # current page — no href
                    ])

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Disabled links drop ``href=`` (keyboard can't "
                        "navigate), set ``aria-disabled=\"true\"``, and "
                        "remove themselves from the focus order via "
                        "``tabindex=\"-1\"`` so screen readers still "
                        "announce them but tab navigation skips. "
                        "External links carry "
                        "``rel=\"noopener noreferrer\"`` to neuter the "
                        "opener and block referrer leakage.",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="sm"):
                        ui.link("Active link",     href="/")
                        ui.link("Disabled link",   href="/",
                                disabled=True)
                        ui.link("External target", href="https://example.com",
                                external=True)

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
                        "Mirror of Link's ``BINDABLE_PROPS = "
                        "('label', 'href')`` contract. the runtime swaps "
                        "the inner ``bz-text`` (label) AND the "
                        "``bz-attr:href`` attribute on every state "
                        "mutation — no network round-trip. Visual "
                        "props (variant / color / external / disabled) "
                        "stay static.",
                        color="muted", size="sm",
                    )
                    client = LinkClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("label"):
                            ui.input(value=client.label,
                                     placeholder="Live destination")
                        with control("href"):
                            ui.input(value=client.href,
                                     placeholder="/button")

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.link(client.label, href=client.href,
                                color="primary",
                                variant="underline")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;span bz-text&gt; inside "
                        "the &lt;a&gt;, plus an bz-attr:href "
                        "directive that rewrites the destination as "
                        "the bound state mutates.",
                        serialize_html(
                            ui.link(client.label, href=client.href,
                                    color="primary",
                                    variant="underline")
                        ),
                    )
