"""``IFrame`` test bench.

Seven cards: the sandbox / title & ratio / Reference / Composability /
Edge cases / A11y / Server playground. ``BINDABLE_PROPS = ()`` and
``EVENTS = ()`` so no Client card and no event.

The component's only real question is its **default sandbox**: card 1 is
entirely devoted to it.

⚠️ Entirely offline — the frames use ``srcdoc`` (an inline document, zero
network requests). It is the video bench's lesson: a dummy path is not
"staying offline", it is one 404 per element.
"""

from bretzel import refreshable, ui
from bretzel.components import SANDBOX_BASELINE
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/iframe"

RATIOS = ["square", "video", "portrait", "wide"]


def doc(body: str, bg: str = "#f8fafc") -> str:
    """An inline document for ``srcdoc`` — no network request."""
    return (
        f"<body style=\"margin:0;background:{bg};font-family:sans-serif;"
        f"display:flex;align-items:center;justify-content:center;"
        f"height:100vh;color:#0f172a\">{body}</body>"
    )


DOC_MAP = doc('<strong>A map would go here</strong>', "#e0f2fe")
DOC_FORM = doc('<em>A payment widget would go here</em>', "#fef3c7")
DOC_PLAIN = doc('Embedded document')


class EmbedPlayground(PageState):
    """The server bench's state — iframe only (audio has not enough
    surface to deserve a panel)."""

    ratio: str = field(default="video")
    title: str = field(default='Demonstration document')
    sandbox_mode: str = field(default="baseline")
    custom_sandbox: str = field(default="allow-scripts")
    classes: str = field(default="")
    custom_id: str = field(default="")
    visible: str = field(default="on")


def server_changed(state: EmbedPlayground) -> None:
    pass


def build_preview(state: EmbedPlayground):
    kwargs: dict = {"title": state.title}
    if state.ratio:
        kwargs["ratio"] = state.ratio
    if state.sandbox_mode == "custom":
        kwargs["sandbox"] = state.custom_sandbox
    elif state.sandbox_mode == "maximal":
        kwargs["sandbox"] = ""
    elif state.sandbox_mode == "none":
        kwargs["sandbox"] = None
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.iframe(attrs={"srcdoc": DOC_PLAIN}, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[EmbedPlayground])
def server_panel() -> None:
    state = EmbedPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("title (obligatoire)"):
            ui.input(value=state.title, placeholder='Describe the frame',
                     on_change=server_changed)
        with control("ratio"):
            ui.select(value=state.ratio,
                      options=[("", "aucun")] + [(r, r) for r in RATIOS],
                      on_change=server_changed)
        with control("sandbox"):
            ui.select(value=state.sandbox_mode,
                      options=[("baseline", 'default (Bretzel base)'),
                               ("custom", "liste explicite"),
                               ("maximal", 'sandbox="" — everything refused'),
                               ("none", "None — aucune restriction")],
                      on_change=server_changed)
        with control("liste explicite (si sandbox=liste)"):
            ui.input(value=state.custom_sandbox,
                     placeholder="allow-scripts",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="rounded-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-frame",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", 'False (nothing rendered)')],
                      on_change=server_changed)

    ui.divider()

    with ui.vstack(classes="max-w-md"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("IFrame", level=1)
            ui.text(
                'A third-party document, bounded by default. The '
                    "component's only real question is its sandbox — Bretzel "
                    'sets one even when you do not ask, and the card below '
                    'explains which and why.',
                color="muted",
            )
            ui.text(
                'A fully offline page: the frames use srcdoc, an inline '
                    'document, hence zero network requests.',
                color="muted", size="sm",
            )

            # ── Carte 1 — IFrame : le sandbox ───────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading('The default sandbox', level=2)
                    ui.text(
                        'Bretzel sets a sandbox even when you do not ask '
                            'for one. The point is not what the list allows, '
                            'it is what it LEAVES OUT: as soon as a sandbox '
                            'attribute exists, top-level navigation and '
                            'downloads are refused until they are asked for. '
                            'Those are the two vectors that turn an embed '
                            'into phishing.',
                        color="muted", size="sm",
                    )
                    ui.code(SANDBOX_BASELINE, lang="text")
                    ui.text(
                        'The four permissions granted are the ones '
                            'without which a map, a player or a payment '
                            'widget do not work at all. A default everybody '
                            'turns off at the first attempt would teach '
                            'exactly one thing: how to turn it off.',
                        color="muted", size="sm",
                    )

                    ui.heading('The three outputs, all explicit',
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.code(
                            'ui.iframe(src, title="…", sandbox="allow-scripts")  # your own list\nui.iframe(src, title="…", sandbox="")               # everything refused\nui.iframe(src, title="…", sandbox=None)             # no restriction at all',
                            lang="python",
                        )

            # ── Carte 2 — IFrame : title et ratio ───────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("title et ratio", level=2)
                    ui.text(
                        'title is mandatory: a screen reader announces '
                            'frames by their title, and without it the user '
                            'hears “frame” without knowing whether it is a '
                            'map or a payment form. The same reason as '
                            "ui.image's alt — the omission is invisible on "
                            'screen.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'ratio reserves the height. An embed is the '
                            'leading cause of page jump, and an iframe with '
                            'no dimensions falls back to a 300×150 inherited '
                            'from the nineties.',
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ratio=video", size="xs", color="muted")
                            ui.iframe(title='Demonstration card',
                                      ratio="video",
                                      attrs={"srcdoc": DOC_MAP})
                        with ui.vstack(gap="xs"):
                            ui.text("ratio=square", size="xs", color="muted")
                            ui.iframe(title='Demonstration payment',
                                      ratio="square",
                                      attrs={"srcdoc": DOC_FORM})

            # ── Carte 3 — Surface d'API ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        'Every parameter of the component, as a literal '
                            'call — that is what the '
                            'test_playground_demos_the_api gate checks.',
                        color="muted", size="sm",
                    )

                    ui.heading('ui.iframe — every parameter', level=3)
                    with ui.vstack(classes="max-w-md", gap="sm"):
                        ui.iframe(
                            src="data:text/html,<p>src explicite</p>",
                            title='A frame with src, ratio and sandbox',
                            ratio="wide",
                            sandbox="allow-scripts",
                        )

                    ui.heading('The four ratios', level=3)
                    with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
                        for name in RATIOS:
                            with ui.vstack(gap="xs"):
                                ui.text(f"ratio={name}", size="xs",
                                        color="muted")
                                ui.iframe(title=f"Cadre {name}",
                                          ratio=name,
                                          attrs={"srcdoc": DOC_PLAIN})

            # ── Carte 4 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading('With no ratio — the 300×150 of the nineties',
                               level=3)
                    ui.text(
                        'This is the native default, and it depends '
                            'neither on the content nor on the container. It '
                            'is here to be recognised: a height that looks '
                            'like nothing you asked for is a forgotten ratio.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(title='A frame with no ratio',
                                  attrs={"srcdoc": DOC_PLAIN})

                    ui.heading("The sandbox's three outputs, rendered",
                               level=3)
                    ui.text(
                        'sandbox="" refuses EVERYTHING: a static document'
                            ' still displays, a script would no longer run in'
                            ' it. sandbox=None removes the attribute, and '
                            'every restriction with it — the frame becomes a '
                            'peer of the page again.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text('default (Bretzel base)', size="xs",
                                    color="muted")
                            ui.iframe(title='Default frame',
                                      ratio="square",
                                      attrs={"srcdoc": DOC_PLAIN})
                        with ui.vstack(gap="xs"):
                            ui.text('sandbox="" — everything refused', size="xs",
                                    color="muted")
                            ui.iframe(title='A locked frame',
                                      ratio="square", sandbox="",
                                      attrs={"srcdoc": DOC_PLAIN})
                        with ui.vstack(gap="xs"):
                            ui.text("sandbox=None — aucune restriction",
                                    size="xs", color="muted")
                            ui.iframe(title="Cadre libre", ratio="square",
                                      sandbox=None,
                                      attrs={"srcdoc": DOC_PLAIN})

                    ui.heading("Source injoignable", level=3)
                    ui.text(
                        'The frame stays empty, but it KEEPS its box: '
                            'that is the whole point of the ratio, the page '
                            'will not jump when the source arrives — or fails'
                            ' to.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(src='/this-route-does-not-exist',
                                  title='A frame whose source fails',
                                  ratio="video")

                    ui.heading('A very long title', level=3)
                    ui.text(
                        'The title is not rendered on screen: it can be '
                            'long without moving anything. That is also why '
                            'its absence is invisible.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(
                            title=(
                                'Fourth-quarter sales dashboard, filtered'
                                    ' on the North East region, updated every'
                                    ' fifteen minutes'
                            ),
                            ratio="video",
                            attrs={"srcdoc": DOC_MAP},
                        )

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading('Inside a constrained grid cell',
                               level=3)
                    with ui.grid(cols={"base": 3}, gap="sm"):
                        for name in ("square", "video", "portrait"):
                            ui.iframe(title=f"Cadre {name}", ratio=name,
                                      attrs={"srcdoc": DOC_PLAIN})

            # ── Carte 6 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "title is the component's ONLY mandatory "
                            'parameter, and it is an accessibility decision: '
                            'a screen reader announces frames by their title,'
                            ' so without it the user hears “frame” without '
                            'knowing whether it is a map or a payment form. '
                            "Like an image's alt, the omission does not show "
                            'on screen — hence the refusal at construct time '
                            'rather than an empty default.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'A title is only useful if it DISTINGUISHES. '
                            '“Frame” or “Embedded content” satisfy the '
                            'constructor and teach nothing: the question it '
                            'answers is “should I go in there?”.',
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text('title="Cadre" — satisfait, inutile',
                                    size="xs", color="muted")
                            ui.iframe(title="Cadre", ratio="video",
                                      attrs={"srcdoc": DOC_FORM})
                        with ui.vstack(gap="xs"):
                            ui.text('title="Paiement par carte — '
                                    'Stripe" — utile',
                                    size="xs", color="muted")
                            ui.iframe(
                                title="Paiement par carte — Stripe",
                                ratio="video",
                                attrs={"srcdoc": DOC_FORM},
                            )

                    ui.heading('The frame is a DOCUMENT, not a widget',
                               level=3)
                    ui.text(
                        'Focus enters it with Tab and carries on inside: '
                            "what is in there escapes Bretzel's theme, "
                            'directives and gates entirely. A third-party '
                            'embed can trap the keyboard without anything '
                            'here knowing — which is also what the default '
                            'sandbox limits.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'ratio plays its part too: a frame that grows '
                            'after the fact shifts what you were aiming at. '
                            'For anyone who points with difficulty, a button '
                            'that moves is not an aesthetic defect.',
                        color="muted", size="sm",
                    )

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Change the sandbox mode and watch the attribute '
                            'appear, change, or vanish in the emitted HTML.',
                        color="muted", size="sm",
                    )
                    server_panel()
