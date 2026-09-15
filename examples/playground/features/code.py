"""``Code`` test bench.

Seven visual cards : Reference / Slots / Edge cases / Composability /
A11y / Server playground / Client playground. ``BINDABLE_PROPS =
(\"text\",)`` — text is bindable (Pygments highlighting drops on the
reactive path ; lang stays design-time).

Two props : ``text`` (positional, str or ClientBinding) and ``lang``
(Pygments lexer name). No events, no slots.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/code"


LANGS = ["python", "javascript", "typescript", "html", "css",
         "json", "bash", "sql", "yaml", "markdown"]


_PY_SAMPLE = '''def hello(name: str) -> str:
    """Greet the user warmly."""
    return f"Hello, {name}!"

print(hello("Bretzel"))'''

_JS_SAMPLE = '''const greet = (name) => {
  console.log(`Hello, ${name}!`);
  return name.length;
};
greet("Bretzel");'''

_HTML_SAMPLE = '''<button class="btn btn-primary"
        bz-attr:disabled="state.busy">
  Save
</button>'''

_BASH_SAMPLE = '''#!/bin/sh
for f in *.py; do
  echo "Linting $f"
  ruff check "$f" || exit 1
done'''


class CodePlayground(PageState):
    text:        str = field(default=_PY_SAMPLE)
    lang:        str = field(default="python")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class CodeClient(ClientState, persist="memory"):
    """Mirror of Code's BINDABLE_PROPS = ('text',). the runtime swaps the
    text in-browser via ``<span bz-text>``."""

    text: str = field(default="print('Bretzel signals = ♥')")


def server_changed(state: CodePlayground) -> None:
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


def build_preview(state: CodePlayground):
    kwargs: dict = {"lang": state.lang}
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
    return ui.code(state.text, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[CodePlayground])
def server_panel() -> None:
    state = CodePlayground()

    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        with control("text (multi-line)"):
            ui.textarea(value=state.text, rows=6,
                        on_change=server_changed)
        with control("lang"):
            ui.select(value=state.lang,
                      options=[(l, l) for l in LANGS],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!text-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-code",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Sample code",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="max-height: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=code",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Copy the snippet",
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
        "Emitted HTML (truncated — Pygments spans not "
        "shown verbatim)",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Code", level=1)
            ui.text(
                "Block code with server-side Pygments syntax "
                "highlighting. Pass a ``ClientBinding`` for the text "
                "and the highlight drops (the binding wins) — the runtime "
                "swaps the inner text on every state mutation. The "
                "Server playground card stress-tests every prop ; "
                "the emitted HTML is shown live underneath.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every supported lang.",
                            color="muted", size="sm")

                    ui.heading("Python", level=3)
                    ui.code(_PY_SAMPLE, lang="python")

                    ui.heading("JavaScript", level=3)
                    ui.code(_JS_SAMPLE, lang="javascript")

                    ui.heading("HTML", level=3)
                    ui.code(_HTML_SAMPLE, lang="html")

                    ui.heading("Bash", level=3)
                    ui.code(_BASH_SAMPLE, lang="bash")

                    ui.heading("JSON", level=3)
                    ui.code('{"name": "Bretzel", "version": 2, '
                            '"runtime": "Bretzel+HTMX"}',
                            lang="json")

                    ui.heading("SQL", level=3)
                    ui.code("SELECT u.id, u.email\n"
                            "FROM users u\n"
                            "WHERE u.active = TRUE\n"
                            "ORDER BY u.created_at DESC\n"
                            "LIMIT 10;",
                            lang="sql")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``text`` is the positional slot. Accepts str "
                        "(highlighted) or ClientBinding (passes through "
                        "the runtime ``bz-text`` — no highlighting).",
                        color="muted", size="sm",
                    )

                    ui.heading("text=str — server-side highlight", level=3)
                    ui.code("print('Bretzel')", lang="python")

                    ui.heading(
                        "text=ClientBinding — client-driven "
                        "(see Client playground below)",
                        level=3,
                    )
                    ui.text(
                        "Bind the text to a ClientState field ; the "
                        "snippet swaps in the browser without a "
                        "network round-trip. No highlighting on the "
                        "reactive path.",
                        color="muted", size="xs",
                    )

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual content shapes.",
                            color="muted", size="sm")

                    ui.heading("Empty text", level=3)
                    ui.code("", lang="python")

                    ui.heading("Single token", level=3)
                    ui.code("True", lang="python")

                    ui.heading("Very long single line (200 chars)", level=3)
                    ui.code("x = " + "1+" * 99 + "1",
                            lang="python")

                    ui.heading("Multi-line with mixed indentation", level=3)
                    ui.code(
                        "def fn():\n"
                        "\tif x:\n"
                        "        # 4 spaces here\n"
                        "        return True\n"
                        "\treturn False",
                        lang="python",
                    )

                    ui.heading("HTML-special characters", level=3)
                    ui.text(
                        "Highlighter escapes < > & — they render "
                        "literally instead of being parsed as tags.",
                        color="muted", size="xs",
                    )
                    ui.code("<script>alert(1)</script>", lang="html")

                    ui.heading("Unicode + emoji", level=3)
                    ui.code(
                        "GREETING = '🚀 שלום 中文 — Bretzel ♥'\n"
                        "print(GREETING)",
                        lang="python",
                    )

                    ui.heading("Unknown lang (falls back to plain escape)",
                               level=3)
                    ui.code("could be brainfuck. could be cobol.",
                            lang="not-a-real-lang")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Code nested inside common containers.",
                            color="muted", size="sm")

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Snippet header",
                                    color="muted", size="xs")
                            ui.code("ui.button('Click me')",
                                    lang="python")

                    ui.heading("Side-by-side (hstack)", level=3)
                    with ui.hstack(align="stretch"):
                        with ui.vstack(gap="xs"):
                            ui.text("Before", color="muted", size="xs")
                            ui.code("x = 1", lang="python")
                        with ui.vstack(gap="xs"):
                            ui.text("After", color="muted", size="xs")
                            ui.code("x: int = 1", lang="python")

                    ui.heading("Inside ui.tooltip (compact)", level=3)
                    with ui.tooltip("Hover for the snippet"):
                        ui.code("ui.text('hovered')", lang="python")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Code renders as a ``<pre><code>`` block so "
                        "screen readers treat it as preformatted text "
                        "with monospace semantics. Override the spoken "
                        "label via the ``aria-label`` control in the "
                        "Server playground.",
                        color="muted", size="sm",
                    )
                    ui.code("# This is preformatted text.\n"
                            "# Try Tab + ↓ in a screen reader.",
                            lang="python",
                            aria_label="Sample preformatted code")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Edit the text, switch the language, toggle "
                        "every escape hatch ; the preview AND the "
                        "framework-emitted HTML refresh on every "
                        "change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 7 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Code's ``BINDABLE_PROPS = "
                        "('text',)`` contract. the runtime swaps the inner "
                        "``<span bz-text>`` on every state mutation — "
                        "no network round-trip. ``lang=`` is "
                        "design-time so no syntax highlighting on the "
                        "reactive path (same trade-off as Text / "
                        "Heading).",
                        color="muted", size="sm",
                    )
                    client = CodeClient()
                    with ui.vstack(gap="md"):
                        with control("text"):
                            ui.textarea(value=client.text, rows=4)

                    ui.divider()

                    with ui.flex(justify="center", align="stretch"):
                        ui.code(client.text, lang="python")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — &lt;pre&gt;&lt;code&gt; with "
                        "an inner &lt;span bz-text&gt; ; no Pygments "
                        "spans on the reactive path.",
                        serialize_html(
                            ui.code(client.text, lang="python")
                        ),
                    )
