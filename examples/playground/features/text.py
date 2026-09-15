"""``Text`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"content\",)`` — only the text content is bindable ; size / weight /
align / italic / decoration / truncate / color stay design-time.

Eight props : ``content`` (positional, str | ClientBinding | Component),
``size``, ``weight``, ``align``, ``italic``, ``decoration``,
``truncate``, ``color``. No events.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/text"


SIZES       = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl"]
WEIGHTS     = ["normal", "medium", "semibold", "bold"]
ALIGNS      = ["left", "center", "right", "justify"]
DECORATIONS = ["none", "underline", "line-through"]
COLORS      = ["primary", "secondary", "success", "warning",
               "error", "info", "muted"]


class TextPlayground(PageState):
    content:     str  = field(default="The quick brown fox jumps over the lazy dog.")
    size:        str  = field(default="md")
    weight:      str  = field(default="normal")
    align:       str  = field(default="left")
    italic:      bool = field(default=False)
    decoration:  str  = field(default="none")
    truncate:    bool = field(default=False)
    color:       str  = field(default="")   # "" = inherit
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class TextClient(ClientState, persist="memory"):
    """Mirror of Text's BINDABLE_PROPS = ('content',)."""

    content: str = field(default="Live content — edit me")


def server_changed(state: TextPlayground) -> None:
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


def build_preview(state: TextPlayground):
    kwargs: dict = {
        "size": state.size,
        "weight": state.weight,
        "align": state.align,
        "italic": state.italic,
        "decoration": state.decoration,
        "truncate": state.truncate,
    }
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
    return ui.text(state.content, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[TextPlayground])
def server_panel() -> None:
    state = TextPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("text"):
            ui.textarea(value=state.content, rows=3,
                        on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("weight"):
            ui.select(value=state.weight,
                      options=[(w, w) for w in WEIGHTS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.align,
                      options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("italic"):
            ui.switch(checked=state.italic, on_change=server_changed)
        with control("decoration"):
            ui.select(value=state.decoration,
                      options=[(d, d) for d in DECORATIONS],
                      on_change=server_changed)
        with control("truncate"):
            ui.switch(checked=state.truncate, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[("", "inherit")]
                              + [(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!tracking-wider",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-text",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Helper text",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="letter-spacing: 0.05em",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=text",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Hover for help",
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
            ui.heading("Text", level=1)
            ui.text(
                "Inline / block text primitive — polymorphic over the "
                "underlying HTML tag (``span`` by default). Quick "
                "visual reference below ; the real stress-testing "
                "lives in the Server playground card where every prop "
                "is wired to a control and the emitted HTML refreshes "
                "live underneath the preview.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Sizes", level=3)
                    with ui.vstack(gap="sm"):
                        for s in SIZES:
                            ui.text(f"{s} — the quick brown fox", size=s)

                    ui.heading("Weights", level=3)
                    with ui.hstack(gap="lg"):
                        for w in WEIGHTS:
                            ui.text(w.title(), weight=w)

                    ui.heading("Colors", level=3)
                    with ui.hstack(wrap=True):
                        for c in COLORS:
                            ui.text(c.title(), color=c)

                    ui.heading("Alignment", level=3)
                    with ui.vstack(gap="sm"):
                        ui.text("Left aligned text — the default.",
                                align="left")
                        ui.text("Center aligned text.", align="center")
                        ui.text("Right aligned text.",  align="right")
                        ui.text("Justified text that stretches to "
                                "fill its container width.",
                                align="justify")

                    ui.heading("Decoration", level=3)
                    with ui.hstack(gap="lg"):
                        for d in DECORATIONS:
                            ui.text(d, decoration=d)

                    ui.heading("Italic", level=3)
                    with ui.hstack(gap="lg"):
                        ui.text("Roman")
                        ui.text("Italic", italic=True)

                    ui.heading("Truncate", level=3)
                    with ui.flex(classes="max-w-xs"):
                        ui.text(
                            "A very long line of prose that will be "
                            "cut with an ellipsis when the container "
                            "forces it onto a single row — useful in "
                            "tables, cards, list items.",
                            truncate=True,
                        )

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``content`` is the positional slot. Accepts "
                        "str (literal), ClientBinding (live), or "
                        "another Component (nested formatting).",
                        color="muted", size="sm",
                    )

                    ui.heading("content=str", level=3)
                    ui.text("Plain literal string.")

                    ui.heading("content=Component (nested Text)", level=3)
                    ui.text(
                        ui.text("Inner styled span",
                                color="success", weight="bold"),
                    )

                    ui.heading(
                        "content=ClientBinding — see Client playground",
                        level=3,
                    )
                    ui.text(
                        "Bind to a ClientState string ; the runtime swaps "
                        "the inner ``bz-text`` on every mutation. No "
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
                    ui.text("")

                    ui.heading("Very long single word (truncates)",
                               level=3)
                    with ui.flex(classes="max-w-xs"):
                        ui.text("A" * 80, truncate=True)

                    ui.heading("Emoji + multi-script", level=3)
                    ui.text("Ship 🚀 — שלום — 中文 — مرحبا — π ≈ 3.14")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Framework escapes the content — the script "
                        "renders as literal text instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.text("<script>alert(1)</script>")

                    ui.heading("All modifiers stacked", level=3)
                    ui.text(
                        "Big bold italic muted underlined",
                        size="2xl", weight="bold", italic=True,
                        decoration="underline", color="muted",
                    )

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Text nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Title", weight="bold")
                            ui.text("Body copy paragraph.",
                                    color="muted")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip("Helper explanation"):
                        ui.text("Hover for a tooltip",
                                decoration="underline", color="primary")

                    ui.heading("Inside ui.hstack (label + value)", level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.text("Status:", color="muted")
                        ui.text("Active", color="success", weight="bold")

                    ui.heading("Mixed with ui.icon", level=3)
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon("info", color="info")
                        ui.text("Heads-up message", color="info")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Text emits a ``<span>`` by default — inline-"
                        "neutral, no implicit landmark role. For "
                        "paragraphs / labels / headings, use the "
                        "``tag=`` override (``ui.text('…', tag='p')``) "
                        "or the dedicated ``ui.heading()`` / ``ui."
                        "label()`` primitives.",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="sm"):
                        ui.text("Default tag is <span> (inline).")
                        ui.text("Use tag='p' for paragraphs.",
                                tag="p", color="muted")

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
                        "Mirror of Text's ``BINDABLE_PROPS = "
                        "('content',)`` contract. the runtime swaps the "
                        "inner ``bz-text`` on every state mutation — "
                        "no network round-trip. Visual props (size / "
                        "weight / italic / decoration / etc.) stay "
                        "static.",
                        color="muted", size="sm",
                    )
                    client = TextClient()
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with control("text"):
                            ui.input(value=client.content,
                                     placeholder="Live content")

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.text(client.content, color="primary",
                                weight="bold")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;span bz-text&gt; bound to "
                        "$bz.state.TextClient.default.content. Each "
                        "keystroke in the input rewrites the inner "
                        "text without a network round-trip.",
                        serialize_html(
                            ui.text(client.content, color="primary",
                                    weight="bold")
                        ),
                    )
