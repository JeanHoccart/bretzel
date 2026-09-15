"""``Heading`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"content\",)`` — only the text content is bindable ; level / size /
weight / color stay design-time.

Five props : ``content`` (positional, str | ClientBinding | Component),
``level`` (1-6, HTML tag), ``size`` (auto from level), ``weight``,
``color``. No events.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/heading"


LEVELS  = [1, 2, 3, 4, 5, 6]
SIZES   = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl",
           "5xl", "6xl", "7xl"]
WEIGHTS = ["normal", "medium", "semibold", "bold"]
COLORS  = ["primary", "secondary", "success", "warning",
           "error", "info", "muted"]


class HeadingPlayground(PageState):
    content:     str = field(default="Section title")
    level:       int = field(default=2)
    size:        str = field(default="")   # "" = auto from level
    weight:      str = field(default="bold")
    color:       str = field(default="")   # "" = inherit
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class HeadingClient(ClientState, persist="memory"):
    """Mirror of Heading's BINDABLE_PROPS = ('content',)."""

    content: str = field(default="Live title")


def server_changed(state: HeadingPlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state;
    # ``level`` coerces to int via its field type.
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


def build_preview(state: HeadingPlayground):
    kwargs: dict = {
        "level": state.level,
        "weight": state.weight,
    }
    if state.size:
        kwargs["size"] = state.size
    if state.color:
        kwargs["color"] = state.color
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
    return ui.heading(state.content, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[HeadingPlayground])
def server_panel() -> None:
    state = HeadingPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("text"):
            ui.input(value=state.content, placeholder="Section title",
                     on_change=server_changed)
        with control("level"):
            ui.select(value=state.level,
                      options=[(l, f"h{l}") for l in LEVELS],
                      on_change=server_changed)
        with control("size (empty = auto from level)"):
            ui.select(value=state.size,
                      options=[("", "auto")]
                              + [(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("weight"):
            ui.select(value=state.weight,
                      options=[(w, w) for w in WEIGHTS],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[("", "inherit")]
                              + [(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!italic !underline",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="section-A",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Section A heading",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="letter-spacing: 0.05em",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=heading",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Section title",
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
            ui.heading("Heading", level=1)
            ui.text(
                "Semantic h1–h6 with size decoupled from level. The "
                "HTML tag follows ``level=`` (SEO / a11y) ; the "
                "visual size follows ``size=`` or auto-derives from "
                "the level. The Server playground card stress-tests "
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

                    ui.heading("Levels (h1 → h6, auto sizes)", level=3)
                    with ui.vstack(gap="sm"):
                        ui.heading("Level 1 — auto",  level=1)
                        ui.heading("Level 2 — auto",  level=2)
                        ui.heading("Level 3 — auto",  level=3)
                        ui.heading("Level 4 — auto",  level=4)
                        ui.heading("Level 5 — auto",  level=5)
                        ui.heading("Level 6 — auto",  level=6)

                    ui.heading("Size override (decoupled from level)",
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.heading("h2 forced to xs",  level=2, size="xs")
                        ui.heading("h2 forced to md",  level=2, size="md")
                        ui.heading("h2 forced to xl",  level=2, size="xl")
                        ui.heading("h2 forced to 3xl", level=2, size="3xl")
                        ui.heading("h2 forced to 5xl", level=2, size="5xl")

                    ui.heading("Weights", level=3)
                    with ui.vstack(gap="sm"):
                        ui.heading("Normal weight",   level=3, weight="normal")
                        ui.heading("Medium weight",   level=3, weight="medium")
                        ui.heading("Semibold weight", level=3, weight="semibold")
                        ui.heading("Bold weight",     level=3, weight="bold")

                    ui.heading("Colors", level=3)
                    with ui.vstack(gap="sm"):
                        for c in COLORS:
                            ui.heading(c.title(), level=4, color=c)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``content`` is the positional slot. Accepts "
                        "str (literal), ClientBinding (live), or "
                        "another Component (nested icon / badge).",
                        color="muted", size="sm",
                    )

                    ui.heading("content=str", level=3)
                    ui.heading("Plain string", level=3)

                    ui.heading("content=Component (nested Text)", level=3)
                    ui.heading(
                        ui.text("Custom italic span", classes="italic"),
                        level=3,
                    )

                    ui.text(
                        "content=ClientBinding — see Client playground",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Bind to a ClientState string ; the runtime swaps "
                        "the inner span on every mutation. No network "
                        "round-trip.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Content shapes that historically break "
                            "primitives.",
                            color="muted", size="sm")

                    ui.heading("Empty content", level=3)
                    ui.heading("", level=2)

                    ui.heading("Very long content (120 chars)", level=3)
                    ui.heading("A" * 120, level=3)

                    ui.heading("Emoji + multi-script", level=3)
                    ui.heading("Ship 🚀 — שלום — 中文 — مرحبا", level=2)

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes — the script renders as "
                        "literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.heading("<script>alert(1)</script>", level=3)

                    ui.heading("h1 visually muted to xs", level=3)
                    ui.heading("Visually tiny but still an h1",
                               level=1, size="xs", color="muted")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Heading nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Card title", level=2)
                            ui.text("Card body copy here.", color="muted")

                    ui.heading("Inside ui.hstack with sibling icon",
                               level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon("flag", color="primary")
                        ui.heading("Section flag", level=3)

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Click to navigate"):
                        ui.heading("Tooltipped heading", level=4,
                                   color="primary")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "``level=`` drives the actual ``<h1>``…``<h6>`` "
                        "tag so screen readers and SEO tooling get the "
                        "right hierarchy. The visual size is a "
                        "separate axis — don't pick the level to look "
                        "right, pick it to be right.",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="sm"):
                        ui.heading("Page title (h1)",      level=1)
                        ui.heading("Major section (h2)",   level=2)
                        ui.heading("Subsection (h3)",      level=3)
                        ui.heading("Sub-subsection (h4)",  level=4)

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
                        "Mirror of Heading's ``BINDABLE_PROPS = "
                        "('content',)`` contract. the runtime swaps the "
                        "inner ``<span bz-text>`` on every state "
                        "mutation — no network round-trip. Visual "
                        "props (level / size / weight / color) stay "
                        "static.",
                        color="muted", size="sm",
                    )
                    client = HeadingClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("text"):
                            ui.input(value=client.content,
                                     placeholder="Live title")

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.heading(client.content, level=2, color="primary")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;h2&gt; wraps a &lt;span "
                        "bz-text&gt; bound to "
                        "$bz.state.HeadingClient.default.content.",
                        serialize_html(
                            ui.heading(client.content, level=2,
                                       color="primary")
                        ),
                    )
