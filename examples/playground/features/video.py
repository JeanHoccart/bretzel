"""``Video`` test bench.

Seven cards: Reference / Ratios / The autoplay guard / Edge cases /
Composability / A11y / Server playground. BINDABLE_PROPS = () so no
Client card.

The component's scope: a native <video> DRESSED UP, not a player. The
controls are the browser's.

⚠️ NO source, and not a dummy path either: this page's <video> have no
src attribute at all. An .mp4 in the repository would weigh for nothing,
a remote URL would make the probes depend on the network — and a
non-existent path, which this bench's v1 used, makes the server take
DOZENS of 404 at every load (seen in the dev logs). What one sees is the
poster (an SVG in a data:) in its box at the declared ratio: exactly the
"before the video arrives" state, for zero requests.
"""

from urllib.parse import quote

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/video"

RATIOS = ["square", "video", "portrait", "wide"]
FITS = ["contain", "cover"]


def poster_source(width: int, height: int, fill: str, label: str) -> str:
    """A poster SVG in a data: — deterministic and offline.

    The # are escaped: an unescaped # in a data: URI cuts the URL on a
    fragment, and the SVG's right half would be lost.
    """
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' "
        f"height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect width='100%' height='100%' fill='{fill}'/>"
        f"<circle cx='{width // 2}' cy='{height // 2}' r='28' "
        f"fill='white' fill-opacity='0.9'/>"
        f"<polygon points='{width // 2 - 8},{height // 2 - 14} "
        f"{width // 2 - 8},{height // 2 + 14} {width // 2 + 16},{height // 2}' "
        f"fill='{fill}'/>"
        f"<text x='50%' y='88%' font-family='sans-serif' font-size='16' "
        f"fill='white' text-anchor='middle'>{label}</text></svg>"
    )
    return "data:image/svg+xml;utf8," + svg.replace("#", "%23")


def vtt_source(cue: str) -> str:
    """A WebVTT file in a data: — the same reason as the poster.

    A track served from the network would make the bench depend on it,
    and a non-existent path would take one 404 per track per load. Here
    the browser really loads the track: the CC menu lists it, and
    ``textTracks[0].cues.length`` is 1.
    """
    body = f"WEBVTT\n\n00:00.000 --> 00:05.000\n{cue}"
    return "data:text/vtt;charset=utf-8," + quote(body)


CAPTION_TRACKS = [
    ui.track(vtt_source('Welcome to Bretzel.'),
             srclang="fr", label='French', default=True),
    ui.track(vtt_source("Welcome to Bretzel."),
             srclang="en", label="English"),
    ui.track(vtt_source('A page of code on a dark background.'),
             srclang="fr", label="Audiodescription", kind="descriptions"),
]

POSTER_WIDE = poster_source(480, 270, "#1e293b", "poster 480x270")
POSTER_TALL = poster_source(270, 480, "#4c1d95", "poster 270x480")
# NO source. Not "an absent path" — no src at all.
#
# This bench's v1 pointed its 16 <video> at a non-existent
# /media/demo-absente.mp4, believing it stayed "offline". The result,
# visible in the dev server's logs: DOZENS of GET 404 per page load,
# every element asking for its source and the browser retrying. A bench
# must not hammer the server to demonstrate an empty box.
#
# With no src, the component does not emit the attribute at all (it NEVER
# puts src="" — an empty attribute resolves against the document's URL,
# so the browser would re-download the page as media). Zero requests, and
# the poster + the ratio box show exactly the same: it is indeed the
# "before the video arrives" state we want to show.
SRC = None


class VideoPlayground(PageState):
    """The server bench's state — one field per prop + per escape hatch."""

    poster: str = field(default="wide")
    ratio: str = field(default="video")
    fit: str = field(default="contain")
    controls: str = field(default="on")
    autoplay: str = field(default="off")
    loop: str = field(default="off")
    muted: str = field(default="off")
    tracks: str = field(default="off")
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    visible: str = field(default="on")
    tooltip: str = field(default="")


POSTERS = {"wide": POSTER_WIDE, "tall": POSTER_TALL, "none": ""}


def server_changed(state: VideoPlayground) -> None:
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


def build_preview(state: VideoPlayground):
    kwargs: dict = {
        "fit": state.fit,
        "controls": state.controls == "on",
        "autoplay": state.autoplay == "on",
        "loop": state.loop == "on",
        "muted": state.muted == "on",
    }
    if state.tracks == "on":
        kwargs["tracks"] = CAPTION_TRACKS
    if state.ratio:
        kwargs["ratio"] = state.ratio
    if POSTERS.get(state.poster):
        kwargs["poster"] = POSTERS[state.poster]
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
    return ui.video(**kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


ON_OFF = [("on", "True"), ("off", "False")]


@refreshable(deps=[VideoPlayground])
def server_panel() -> None:
    state = VideoPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("poster"):
            ui.select(value=state.poster,
                      options=[("wide", "480×270"), ("tall", "270×480"),
                               ("none", "aucun")],
                      on_change=server_changed)
        with control('ratio — IT is what decides the shape'):
            ui.select(value=state.ratio,
                      options=[("", "aucun (taille naturelle)")]
                      + [(r, r) for r in RATIOS],
                      on_change=server_changed)
        with control("fit"):
            ui.select(value=state.fit,
                      options=[(f, f) for f in FITS],
                      on_change=server_changed)
        with control("controls"):
            ui.select(value=state.controls, options=ON_OFF,
                      on_change=server_changed)
        with control("autoplay (force muted)"):
            ui.select(value=state.autoplay, options=ON_OFF,
                      on_change=server_changed)
        with control("muted"):
            ui.select(value=state.muted, options=ON_OFF,
                      on_change=server_changed)
        with control("loop"):
            ui.select(value=state.loop, options=ON_OFF,
                      on_change=server_changed)
        with control("tracks (3 pistes)"):
            ui.select(value=state.tracks, options=ON_OFF,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="rounded-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-video",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder='Product demo',
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.8",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="preload=none",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder='Click to play',
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", 'False (nothing rendered)')],
                      on_change=server_changed)

    ui.divider()

    ui.text(
        f"poster {state.poster} → ratio={state.ratio or 'aucun'}"
        f" · fit={state.fit}"
        f" · autoplay={state.autoplay} → muted rendu="
        f"{'on' if (state.autoplay == 'on' or state.muted == 'on') else 'off'}",
        size="xs", color="muted",
    )

    with ui.vstack(classes="max-w-sm"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Video", level=1)
            ui.text(
                'A dressed-up native <video>, not a player: the controls '
                    "stay the browser's. What the component brings is the "
                    'reserved space (ratio), the poster, and two native traps'
                    ' absorbed — autoplay forces muted, and playsinline is '
                    'always emitted.',
                color="muted",
            )
            ui.text(
                'No real source on this page: the .mp4 paths are missing '
                    'on purpose, so the bench stays offline. What you see is '
                    'the poster and the box — that is, exactly the state '
                    'BEFORE the video arrives.',
                color="muted", size="sm",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading('With a poster and controls (the default)',
                               level=3)
                    with ui.vstack(classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video")

                    ui.heading('With no poster — the dark box', level=3)
                    ui.text(
                        'This is the waiting state: the space is '
                            'reserved, nothing jumps when the video arrives.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.video(ratio="video")

            # ── Carte 2 — Ratios ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Ratios", level=2)
                    ui.text(
                        'The same poster in all four ratios. The shape '
                            'comes from the ratio, never from the source — '
                            'the same rule as ui.image.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'Seen in the browser: in wide (21/9) inside a '
                            'narrow column, the native control bar takes '
                            'almost the whole box — it has a minimum height '
                            'the component cannot reduce. A very flat ratio '
                            'goes with a generous width, or with '
                            'controls=False.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
                        for name in RATIOS:
                            with ui.vstack(gap="xs"):
                                ui.text(name, size="xs", color="muted")
                                ui.video(poster=POSTER_WIDE,
                                         ratio=name)

            # ── Carte 3 — La garde autoplay ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading('The autoplay guard', level=2)
                    ui.text(
                        'Every browser blocks autoplay with sound. With '
                            'no guard, the video simply does not start — no '
                            'error, no log, no visual clue. So the component '
                            'forces muted as soon as autoplay is asked for, '
                            'and writes it into the HTML rather than shipping'
                            ' an inert attribute.',
                        color="muted", size="sm",
                    )
                    ui.heading('autoplay=True, muted not specified', level=3)
                    ui.text('The emitted HTML carries both:',
                            color="muted", size="xs")
                    ui.code(
                        serialize_html(
                            ui.video(autoplay=True, loop=True,
                                     controls=False, ratio="wide",
                                     poster=POSTER_WIDE)
                        ),
                        lang="html",
                    )

                    ui.heading("playsinline, toujours", level=3)
                    ui.text(
                        'Never a prop. Without it, iOS takes the video '
                            'out of the flow and seizes the screen as soon as'
                            ' it plays — never what you want in an '
                            'application, and exactly the kind of thing you '
                            'discover on an iPhone in production.',
                        color="muted", size="sm",
                    )

            # ── Carte 4 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading('Missing source — the box holds', level=3)
                    ui.text(
                        'Every video on this page is in that case: the '
                            'ratio reserved the space, so nothing moves.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.video(ratio="video")

                    ui.heading("A poster at the opposite ratio", level=3)
                    ui.text(
                        'A 270×480 poster in a 16/9 box. fit=contain (the'
                            ' default) shows it whole with letterboxing; '
                            'cover would crop it — and cutting the action is '
                            'rarely wanted, hence this default being the '
                            "opposite of ui.image's.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        for fit in FITS:
                            with ui.vstack(gap="xs"):
                                ui.text(f"fit={fit}", size="xs",
                                        color="muted")
                                ui.video(poster=POSTER_TALL,
                                         ratio="video", fit=fit)

                    ui.heading('With neither controls nor autoplay', level=3)
                    ui.text(
                        'Nobody can play it. The component does not '
                            'forbid it — it is a legitimate combination for a'
                            ' code-driven video — but it can be seen here.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.video(controls=False, ratio="video",
                                 poster=POSTER_WIDE)

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading('In a card', level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        for label in ("Getting started", "What's new"):
                            with ui.card():
                                with ui.vstack(gap="sm"):
                                    ui.video(poster=POSTER_WIDE,
                                             ratio="video")
                                    ui.text(label, weight="bold")
                                    ui.text("2 min", color="muted",
                                            size="sm")

                    ui.heading('Inside a constrained grid cell',
                               level=3)
                    with ui.grid(cols={"base": 3}, gap="sm"):
                        for name in ("square", "video", "portrait"):
                            ui.video(poster=POSTER_TALL, ratio=name)

            # ── Carte 6 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        'controls=True by default, and that is the '
                            "component's accessibility decision: the "
                            "platform's default is “no controls”, which "
                            'leaves an element nobody can reach from the '
                            'keyboard. The controls rendered are the '
                            "browser's — already labelled, already tabbable, "
                            "already announced in the system's language. "
                            'Redrawing them would mean reimplementing them, '
                            'keyboard included.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'The autoplay guard has a second reason, beyond '
                            "the browser's own block: sound that starts by "
                            "itself drowns a screen reader's voice, and the "
                            'user then has no easy way to find what to stop.',
                        color="muted", size="sm",
                    )

                    ui.heading('poster is not alternative text',
                               level=3)
                    ui.text(
                        '<video> has no alt attribute, and the poster is '
                            'one more image, decorative. What describes the '
                            'video must live BESIDE it, as real text — '
                            'readable by everyone, including before the video'
                            ' loads.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video")
                        ui.text('Getting started with Bretzel — 2 min: create a '
                            'page, wire a typed state, mutate.',
                                color="muted", size="sm")

                    ui.heading('Subtitles — tracks=', level=3)
                    ui.text(
                        'The component stays a leaf: the tracks are DATA,'
                            ' not children. A correct track wants three '
                            'attributes, and ui.track demands all three — a '
                            'track with no language and no label does not '
                            'build, so it cannot turn up nameless in the '
                            "browser's menu.",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video",
                                 tracks=CAPTION_TRACKS)
                    ui.text(
                        'Three tracks above: two subtitle languages and '
                            'one audio description. The files are data: URIs,'
                            " so the page stays offline — the browser's CC "
                            'menu really does list them.',
                        color="muted", size="xs",
                    )

                    ui.heading('What the component does NOT provide',
                               level=3)
                    ui.text(
                        'kind="metadata" is refused: it only addresses JS'
                            ' (hover thumbnails, markers for a home-made '
                            'player) and ui.video is not a player. No '
                            'multiple sources either — a single src, and the '
                            'day several formats come up, it will be a '
                            'sources= on the tracks= model.',
                        color="muted", size="xs",
                    )

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Every prop AND every escape hatch is wired to a '
                            'control. Set autoplay to True and watch muted '
                            'appear in the emitted HTML.',
                        color="muted", size="sm",
                    )
                    server_panel()
