"""``Html`` test bench — the way out.

Six cards: Reference / What it unlocks / Security / Edge cases /
Composability / Server playground. ``BINDABLE_PROPS = ()`` so no Client
card — and the constructor REJECTS a ``ClientBinding``, which the
Security card shows.

A single prop (``content``), no event.

⚠️ Every example is **offline**: inline SVG, ``<iframe srcdoc>``,
``<video>`` / ``<audio>`` with no remote source. A bench that depends on
the network makes the probes intermittent and one no longer knows whether
the red comes from the component or from DNS.

⚠️ No card injects a real ``<script>``. The danger is DESCRIBED and
demonstrated by contrast with ``ui.markdown``; running it in a demo page
would dirty the console and set the wrong example.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/html"

SVG_SNIPPET = (
    "<svg width='120' height='120' viewBox='0 0 120 120' "
    "xmlns='http://www.w3.org/2000/svg'>"
    "<circle cx='60' cy='60' r='50' fill='#7c3aed'/>"
    "<text x='60' y='68' text-anchor='middle' fill='white' "
    "font-family='sans-serif' font-size='18'>SVG</text></svg>"
)

IFRAME_SNIPPET = (
    "<iframe title='Embedded document' width='100%' height='120' "
    "style='border:1px solid rgba(128,128,128,.4);border-radius:8px' "
    "srcdoc=\"<p style='font-family:sans-serif;padding:12px'>"
    "I am a document inside an iframe.</p>\"></iframe>"
)

VIDEO_SNIPPET = (
    "<video controls width='260' "
    "style='border-radius:8px;background:#111'></video>"
)

AUDIO_SNIPPET = "<audio controls></audio>"

TABLE_SNIPPET = (
    "<table style='border-collapse:collapse'><tr><th style='border:1px "
        "solid rgba(128,128,128,.4);padding:4px 10px'>Key</th><th "
        "style='border:1px solid rgba(128,128,128,.4);padding:4px "
        "10px'>Value</th></tr><tr><td style='border:1px solid "
        "rgba(128,128,128,.4);padding:4px 10px'>region</td><td "
        "style='border:1px solid rgba(128,128,128,.4);padding:4px 10px'>eu-"
        'west-3</td></tr></table>'
)


class HtmlPlayground(PageState):
    """The server bench's state — one field per prop + per escape hatch."""

    content: str = field(default='<b>Some HTML</b> written by hand.')
    tag: str = field(default="div")
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Modificateurs universels.
    visible: str = field(default="on")
    tooltip: str = field(default="")


def server_changed(state: HtmlPlayground) -> None:
    # A typed param → the dispatcher hydrates the changed control's value.
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


def build_preview(state: HtmlPlayground):
    kwargs: dict = {}
    if state.tag:
        kwargs["tag"] = state.tag
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
    return ui.html(state.content, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[HtmlPlayground])
def server_panel() -> None:
    state = HtmlPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('content — injected VERBATIM'):
            ui.textarea(value=state.content, rows=4,
                        placeholder="<b>gras</b>",
                        on_change=server_changed)
        with control("tag (kwarg universel)"):
            ui.select(value=state.tag,
                      options=[("div", 'div (default)'), ("span", "span"),
                               ("section", "section"), ("figure", "figure")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="text-sm italic",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-embed",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder='Embedded content',
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.8",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=embed",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Contenu tiers",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", 'False (nothing rendered)')],
                      on_change=server_changed)

    ui.divider()

    build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Html", level=1)
            ui.text(
                'The escape hatch: injecting markup the framework did not'
                    ' produce. The underlying node had existed from the start'
                    ' and already served four components; it simply was not '
                    'open to application code. It is an XSS sink — the '
                    'content must be a literal you wrote, or a value passed '
                    'through a sanitiser just before.',
                color="muted",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text('The content comes out verbatim, never escaped.',
                            color="muted", size="sm")

                    ui.heading("Balisage simple", level=3)
                    ui.html('<b>bold</b>, <i>italic</i>, <code>some code</code>, '
                        "and a <a href='#top'>link</a>.")

                    ui.heading("tag= change l'enveloppe", level=3)
                    ui.text(
                        'The wrapper exists so the universal kwargs have '
                            'somewhere to land. tag= picks it; nothing '
                            'removes it.',
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="sm"):
                        ui.text('Inline:')
                        ui.html('<b>inside a span</b>', tag="span")

                    ui.heading("classes= s'ajoute au marqueur", level=3)
                    ui.html("<span>Petit et italique.</span>",
                            classes="text-sm italic")

            # ── Card 2 — What it unlocks ───────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Quand l'utiliser — et quand NON", level=2)
                    ui.text(
                        'This page first demonstrated the escape hatch '
                            'with a video, an audio track and an iframe. Two '
                            'days later ui.video, ui.audio and ui.iframe '
                            'existed, and the demonstration was teaching the '
                            'opposite of what one should do. It is corrected '
                            'here — but the lesson is worth writing down: a '
                            'page that explains an API ages with it.',
                        color="muted", size="sm",
                    )

                    ui.heading('What now has its own component', level=3)
                    ui.text(
                        'Video, audio, embedded frames and images no '
                            'longer go through here. Their components carry '
                            'what a ui.html never will: reserved space '
                            '(ratio), a mandatory alt or title, a default '
                            'sandbox, and the autoplay→muted guard.',
                        color="muted", size="xs",
                    )
                    ui.code(
                        "ui.video(src, poster=..., ratio='video')\n"
                        "ui.audio(src)\n"
                        "ui.iframe(src, title='...', ratio='video')\n"
                        "ui.image(src, alt='...', ratio='square')",
                        lang="python",
                    )

                    ui.heading('What is left at the escape hatch', level=3)
                    ui.text(
                        'The markup no component covers — and none '
                            'deserves one as long as a single use asks for '
                            'it.',
                        color="muted", size="xs",
                    )
                    ui.html(
                        "<details style='padding:8px 0'><summary>A native"
                            " &lt;details&gt;</summary><p style='margin:8px 0"
                            " 0'>No Bretzel component renders this "
                            'tag.</p></details>'
                    )

                    ui.heading("SVG inline", level=3)
                    ui.text(
                        'For an image, prefer ui.image — it reserves the '
                            'space and demands an alt. Inline SVG is for what'
                            ' an img tag cannot do: styling or animating the '
                            'inside of the drawing.',
                        color="muted", size="xs",
                    )
                    ui.html(SVG_SNIPPET)

            # ── Card 3 — Security ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading('Security', level=2)
                    ui.text(
                        'Everything that goes in comes out in the page. A'
                            ' string coming from a user and injected here '
                            'executes. This page does not demonstrate that — '
                            'a real script in a demo page dirties the console'
                            ' and sets the wrong example — but the contrast '
                            'below says exactly what changes.',
                        color="muted", size="sm",
                    )

                    ui.heading('The same text, two components', level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text('ui.markdown — escaped, hence safe',
                                    size="xs", color="muted")
                            ui.markdown('<b>This bold stays text.</b>')
                        with ui.vstack(gap="xs"):
                            ui.text('ui.html — interpreted, so the source is '
                                'yours to guarantee',
                                    size="xs", color="muted")
                            ui.html('<b>This bold is really bold.</b>')

                    ui.heading('What the constructor refuses', level=3)
                    ui.text(
                        'A ClientBinding raises: having the runtime write'
                            ' markup from client state would be a client-'
                            'driven XSS sink, and the server would guarantee '
                            'nothing any more. For HTML that changes, keep '
                            'the source in a PageState and re-render the zone'
                            ' — the server stays the author of the markup. A '
                            'Component raises too: content is a markup '
                            'string, not a slot.',
                        color="muted", size="sm",
                    )

                    ui.heading('And the gate', level=3)
                    ui.text(
                        "This repository's ui.html call sites are a "
                            'closed list, checked by '
                            'tests/consistency/test_ui_html_call_sites_are_listed.py.'
                            ' Adding one turns the suite red — that is what '
                            'makes every injection auditable, not the '
                            "component's name.",
                        color="muted", size="sm",
                    )

            # ── Carte 4 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Contenu vide", level=3)
                    ui.text(
                        'The wrapper is rendered anyway: the universal '
                            'kwargs (id, classes, attrs) must have a carrier,'
                            ' even with no content.',
                        color="muted", size="xs",
                    )
                    ui.html("")

                    ui.heading('Malformed HTML', level=3)
                    ui.text(
                        'The framework does not parse, does not repair, '
                            'does not validate. The browser does what it '
                            'usually does — here it closes the tag for you.',
                        color="muted", size="xs",
                    )
                    ui.html('<b>opened with no closing tag')

                    ui.heading("Contenu volumineux", level=3)
                    ui.html(TABLE_SNIPPET)

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        'The component composes like any other — it is '
                            'its CONTENT that escapes the framework, not the '
                            'component itself.',
                        color="muted", size="sm",
                    )

                    ui.heading('In a card, between components',
                               level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.heading("Rapport", level=4)
                            ui.text('Server-generated summary:',
                                    color="muted", size="sm")
                            ui.html(TABLE_SNIPPET)
                            with ui.hstack():
                                ui.badge("brouillon", color="warning")
                                ui.button("Publier", color="primary")

                    ui.heading('Inside a constrained grid cell',
                               level=3)
                    with ui.grid(cols={"base": 2}, gap="md"):
                        ui.html(SVG_SNIPPET)
                        ui.html(TABLE_SNIPPET)

            # ── Carte 6 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        'This is the only component in the catalogue '
                            'whose accessibility is NOT guaranteed, and it is'
                            ' worth saying plainly: the framework does not '
                            'parse the fragment, so it can check nothing in '
                            'it. An <img> with no alt, a skipped heading '
                            'level, a <div> inside a <p> all pass through '
                            'verbatim — and no gate will ever be able to see '
                            'them, since the content only exists at run time.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'Elsewhere, Bretzel carries that burden for you: '
                            'ui.iframe REFUSES to build without a title, '
                            'ui.form_field ties its label to its control. '
                            "Here the burden falls back on the fragment's "
                            'author — that is the price of the escape hatch, '
                            'not an oversight.',
                        color="muted", size="sm",
                    )

                    ui.heading('The same table, twice', level=3)
                    ui.text(
                        'On the left, no structure: a screen reader '
                            'announces six cells without saying which column '
                            'they belong to. On the right, a <th scope="col">'
                            ' and a caption — the same visual rendering, a '
                            'reading that makes sense.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.html(
                            '<table><tr><td>Product</td><td>Stock</td></tr><tr><td>Cable</td><td>12</td></tr></table>'
                        )
                        ui.html(
                            '<table><caption>Stock by '
                                'product</caption><thead><tr><th '
                                'scope="col">Product</th><th '
                                'scope="col">Stock</th></tr></thead><tbody><tr><td>Cable</td><td>12</td></tr></tbody></table>'
                        )

                    ui.heading('tag= avoids an illegal wrapper',
                               level=3)
                    ui.text(
                        'The default wrapper is a neutral <div>: no role,'
                            ' so it neither adds nor removes semantics. But a'
                            ' <div> between a <ul> and its <li> breaks the '
                            'list for a screen reader — tag="ul" puts the '
                            'wrapper IN PLACE OF the parent instead of '
                            'slipping in between.',
                        color="muted", size="xs",
                    )
                    ui.html("<li>premier</li><li>second</li>", tag="ul")

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Type HTML into the content field: it goes '
                            'verbatim into the page. The emitted HTML '
                            'underneath shows the wrapper the component adds.',
                        color="muted", size="sm",
                    )
                    server_panel()
