"""``Markdown`` test bench.

Five visual cards : Reference / Edge cases / Composability / A11y /
Server playground. ``BINDABLE_PROPS = ()`` — Markdown is
server-only ; a binding path would collapse the structure
(headings / lists / tables / etc.) to plain text and silently
mislead the user. For a live preview UX, the Server playground
pattern (textarea ``on_change`` mutates a PageState and ``refresh()``
the panel) is the canonical recipe.

One prop : ``text`` (positional, str). No events, no slots,
no design-time variants.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/markdown"


_KITCHEN_SINK = """# Bretzel Markdown

A primitive for rendering longer-form **typography** without leaving
Python. Use it for *help texts*, in-app documentation, changelogs, or
any place where a stream of authored content beats hand-composing a
dozen ``ui.heading`` / ``ui.text`` calls.

## Lists

Unordered :

- One
- Two with [a link](https://bretzel-py.dev) inside
- Three, with ``inline code``

Ordered :

1. Read the funnel
2. Read the checklist
3. Ship the component

## Fenced code (Pygments via `ui.code`)

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"

print(greet("Bretzel"))
```

```bash
ruff check bretzel/
pytest -m "not e2e"
```

## Quote + horizontal rule

> "The best framework is the one you don't notice."
> — apocryphal

---

## Table

| Component | Bindable props        |
|-----------|-----------------------|
| Code      | text                  |
| Markdown  | text                  |
| Text      | content               |

## Inline formatting

**Bold**, *italic*, ***bold-italic***, ~~strikethrough~~, and a final
[outbound link](https://example.com)."""


_FAQ_QUESTION = """**How does `ui.markdown` handle untrusted input ?**

Two layers of defense :

- Raw HTML in the source is escaped (``<script>`` → ``&lt;script&gt;``)
- URLs in links and images are filtered : ``javascript:``, ``vbscript:``,
  ``file:``, and non-image ``data:`` URLs are rewritten to
  ``#harmful-link``.

You can paste user-authored markdown straight into it and the
component will not execute scripts or load harmful URIs."""


_DIALOG_HELP = """## Keyboard shortcuts

- ``Esc`` — close this dialog
- ``Tab`` / ``Shift+Tab`` — move focus
- ``Enter`` — confirm

Need more help ? See the [docs](https://bretzel-py.dev/help)."""


class MarkdownPlayground(PageState):
    text: str = field(default=_KITCHEN_SINK)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: MarkdownPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted) ;
    # ``deps=[MarkdownPlayground]`` re-renders the panel automatically.
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


def build_preview(state: MarkdownPlayground):
    kwargs: dict = {}
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
    return ui.markdown(state.text, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[MarkdownPlayground])
def server_panel() -> None:
    state = MarkdownPlayground()

    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with control("text (multi-line markdown)"):
            ui.textarea(value=state.text, rows=10,
                        on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="text-sm",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-doc",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Help text",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-height: 300px; overflow: auto",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=doc",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Help context",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with ui.flex(justify="center", align="stretch"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (verbose — every parsed block carries its theme "
        "classes inline)",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Markdown", level=1)
            ui.text(
                "Render markdown text to bretzel-styled HTML. Uses "
                "``mistune`` server-side for parsing and delegates "
                "fenced code blocks to the same Pygments pipeline as "
                "``ui.code``. Embedded HTML and dangerous URLs are "
                "neutralised by default — safe to feed user-authored "
                "input. **Server-only** — Markdown does NOT accept "
                "a ``ClientBinding`` (the structure would collapse "
                "to plain text). For a live preview, bind the "
                "source to a ``PageState`` and ``refresh()`` from "
                "an ``on_change`` handler — see the Server "
                "playground card.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Kitchen-sink document exercising every "
                        "supported element : headings (h1–h6), "
                        "paragraphs, ordered + unordered lists, "
                        "blockquote, fenced code (Pygments), inline "
                        "code, links, table, horizontal rule, strong, "
                        "emphasis, strikethrough.",
                        color="muted", size="sm",
                    )
                    ui.markdown(_KITCHEN_SINK)

            # ── Card 2 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual content shapes.",
                            color="muted", size="sm")

                    ui.heading("Empty text", level=3)
                    ui.markdown("")

                    ui.heading("HTML-special characters (XSS escape)",
                               level=3)
                    ui.text(
                        "Embedded HTML is escaped to text — the tag "
                        "renders literally instead of executing.",
                        color="muted", size="xs",
                    )
                    ui.markdown(
                        "Hello <script>alert(1)</script> world.\n\n"
                        "<img onerror=alert(1) src=x>"
                    )

                    ui.heading("Dangerous URL protocols", level=3)
                    ui.text(
                        "``javascript:``, ``vbscript:``, ``file:`` "
                        "and non-image ``data:`` URLs become "
                        "``#harmful-link``.",
                        color="muted", size="xs",
                    )
                    ui.markdown(
                        "[js](javascript:alert(1)) — "
                        "[vbs](vbscript:msgbox) — "
                        "[data](data:text/html,<script>) — "
                        "[ok](https://example.com)"
                    )

                    ui.heading("Image data URI allowed", level=3)
                    ui.markdown(
                        "![dot](data:image/png;base64,"
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAA"
                        "FxA8FAAAABGdBTUEAALGPC/xhBQAAAA1JREFU"
                        "CB1jYGD4DwABBQECTSj19gAAAABJRU5ErkJggg==)"
                    )

                    ui.heading("Fence without lang", level=3)
                    ui.markdown(
                        "```\n"
                        "plain monospace, no highlight\n"
                        "```"
                    )

                    ui.heading("Fence with unknown lang", level=3)
                    ui.markdown(
                        "```not-a-real-lang\n"
                        "still rendered as text\n"
                        "```"
                    )

                    ui.heading("Unicode + emoji", level=3)
                    ui.markdown(
                        "Ship 🚀 — שלום — 中文 — Bretzel ♥"
                    )

                    ui.heading("Very long paragraph", level=3)
                    ui.markdown("lorem ipsum dolor sit amet " * 30)

            # ── Card 3 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Markdown nested inside common containers.",
                        color="muted", size="sm",
                    )

                    ui.heading("Inside ui.card (FAQ entry)", level=3)
                    with ui.card():
                        ui.markdown(_FAQ_QUESTION)

                    ui.heading("Inside ui.dialog (help text)", level=3)
                    ui.text(
                        "The dialog opens with a ``ui.button`` ; the "
                        "body is a single ``ui.markdown`` call.",
                        color="muted", size="xs",
                    )
                    help_dialog = ui.dialog(title="Keyboard shortcuts",
                                            width="md")
                    with help_dialog:
                        ui.markdown(_DIALOG_HELP)
                    ui.button("Show keyboard shortcuts",
                              icon_left="keyboard",
                              on_click=help_dialog.open())

                    ui.heading("Inside ui.accordion (collapsible doc)",
                               level=3)
                    with ui.accordion(value="overview",
                                      multiple=False):
                        with ui.accordion_item("overview",
                                               label="Overview"):
                            ui.markdown(
                                "This **Accordion** holds long-form "
                                "answers without dumping them all on "
                                "screen at once. Each panel reveals "
                                "its markdown body on click."
                            )
                        with ui.accordion_item("security",
                                               label="Security"):
                            ui.markdown(_FAQ_QUESTION)

            # ── Card 4 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Markdown emits semantic HTML (h1–h6, p, "
                        "ul/ol/li, blockquote, table/thead/tbody/th/td, "
                        "a, code, pre, hr) so screen readers and "
                        "keyboard users get the expected structure. "
                        "Heading levels in the markdown source map "
                        "directly to ``<h1>``..``<h6>`` — author your "
                        "documents with a sensible outline.",
                        color="muted", size="sm",
                    )
                    ui.markdown(
                        "# Top-level title\n\n"
                        "## Section\n\n"
                        "### Subsection\n\n"
                        "Body paragraph with a [keyboard-navigable "
                        "link](https://bretzel-py.dev). Tab focuses the "
                        "anchor ; Enter activates it."
                    )

            # ── Card 5 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Edit the markdown source, toggle every "
                        "escape hatch, watch the live preview AND the "
                        "framework-emitted HTML refresh on every "
                        "change.",
                        color="muted", size="sm",
                    )
                    server_panel()
