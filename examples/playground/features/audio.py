"""``Audio`` test bench — short, because the component is.

Six cards. This bench long had four, pleading that "the template is a
guide, not a quota" — and the argument looked good until one looked at
WHAT was missing: *Edge cases* and *A11y*, on a component whose only real
subject is precisely accessibility (reachable controls, a transcript the
component does not provide). It was not restraint, it was the two most
owed cards. The gate ``test_a_component_page_carries_its_cards`` now
requires them.

What counts, here, is in card 2: **``ui.video``'s autoplay guard does NOT
carry over to audio**, and it is a decision, not an oversight.

⚠️ Offline. The source is a silent WAV generated as a ``data:`` — the
player works, there is simply nothing to hear.
"""

import base64
import struct

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/audio"


def silent_wav(seconds: float = 0.25, rate: int = 8000) -> str:
    """A silent WAV in a ``data:`` — an offline audio source.

    Generated rather than pasted: 2.7 kB of hard-coded base64 would be
    unreadable in a diff, and nobody would know what it contains. Here
    one sees it is silence.
    """
    n = int(rate * seconds)
    # 0x80 = the midpoint of unsigned 8-bit PCM, hence silence.
    body = bytes([0x80]) * n
    header = (
        b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8)
        + b"data" + struct.pack("<I", n)
    )
    return "data:audio/wav;base64," + base64.b64encode(header + body).decode()


SILENT = silent_wav()


class AudioPlayground(PageState):
    """The server bench's state — one field per prop + per escape hatch."""

    controls: str = field(default="on")
    autoplay: str = field(default="off")
    loop: str = field(default="off")
    muted: str = field(default="off")
    classes: str = field(default="")
    custom_id: str = field(default="")
    visible: str = field(default="on")


ON_OFF = [("on", "True"), ("off", "False")]


def server_changed(state: AudioPlayground) -> None:
    pass


def build_preview(state: AudioPlayground):
    kwargs: dict = {
        "controls": state.controls == "on",
        "autoplay": state.autoplay == "on",
        "loop": state.loop == "on",
        "muted": state.muted == "on",
    }
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.audio(SILENT, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[AudioPlayground])
def server_panel() -> None:
    state = AudioPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("controls"):
            ui.select(value=state.controls, options=ON_OFF,
                      on_change=server_changed)
        with control('autoplay (does NOT force muted)'):
            ui.select(value=state.autoplay, options=ON_OFF,
                      on_change=server_changed)
        with control("muted"):
            ui.select(value=state.muted, options=ON_OFF,
                      on_change=server_changed)
        with control("loop"):
            ui.select(value=state.loop, options=ON_OFF,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="rounded-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-audio",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", 'False (nothing rendered)')],
                      on_change=server_changed)

    ui.divider()

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
            ui.heading("Audio", level=1)
            ui.text(
                'The thinnest of the media family, and it owns that: no '
                    'ratio (an audio player has a fixed height, so there is '
                    'no page jump to avoid), no poster, no theme — the bar is'
                    " drawn by the browser. It exists for the family's "
                    'symmetry, and for one default that matters: '
                    'controls=True.',
                color="muted",
            )
            ui.text(
                "This page's source is a silent WAV generated as a data: "
                    'URI — offline, and the player works.',
                color="muted", size="sm",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading('With controls (the default)', level=3)
                    ui.text(
                        'Without them, an audio element is invisible AND '
                            "inaudible. The platform's default (no controls) "
                            'is a trap for everybody except whoever drives '
                            'playback from JS.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src=SILENT, controls=True)

                    ui.heading('Every parameter, as a literal call',
                               level=3)
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src=SILENT, controls=True, loop=True,
                                 muted=True, autoplay=False)

            # ── Card 2 — The guard that does not carry over ─────────
            with ui.card():
                with ui.vstack():
                    ui.heading('The guard that does not travel',
                               level=2)
                    ui.text(
                        'ui.video forces muted as soon as autoplay is '
                            'asked for, because browsers block autoplay with '
                            'sound. Forcing silence SAVES the playback there:'
                            ' the picture stays, and that was the point.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        'ui.audio does not do it, and that is not an '
                            'oversight. On sound, silence removes everything '
                            'playing brought — you would ship a player '
                            'running for nothing. Autoplay stays blocked '
                            'anyway until the user has interacted with the '
                            'page; no attribute works round that browser '
                            'policy.',
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ui.video(autoplay=True) →",
                                    size="xs", color="muted")
                            ui.code(
                                serialize_html(
                                    ui.video(autoplay=True, ratio="video")
                                ),
                                lang="html",
                            )
                        with ui.vstack(gap="xs"):
                            ui.text("ui.audio(autoplay=True) →",
                                    size="xs", color="muted")
                            ui.code(
                                serialize_html(ui.audio(autoplay=True)),
                                lang="html",
                            )

            # ── Carte 3 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading('controls=False — the element DISAPPEARS',
                               level=3)
                    ui.text(
                        'This is not "a player without buttons": an '
                            '<audio> with no controls has zero height, so the'
                            ' line below is empty. The combination stays '
                            'legitimate — a track driven from JS — but it can'
                            ' only be seen here.',
                        color="muted", size="xs",
                    )
                    with ui.container(
                        classes="p-2 rounded-lg border border-text/10"
                    ):
                        ui.audio(src=SILENT, controls=False)

                    ui.heading("Source absente", level=3)
                    ui.text(
                        'The player still draws itself, with a duration '
                            'of zero. The component does not stand in for a '
                            'missing source — it has nothing to put there.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio()

                    ui.heading("Source illisible", level=3)
                    ui.text(
                        'A truncated data: URI: the browser renders an '
                            'inert player. No error comes back to the server '
                            '— it is a purely client-side failure.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src="data:audio/wav;base64,UklGRg==")

                    ui.heading("autoplay + loop + muted ensemble",
                               level=3)
                    ui.text(
                        'All three coexist without the component '
                            'arbitrating. The emitted HTML shows it: no '
                            'guard, no rewriting.',
                        color="muted", size="xs",
                    )
                    ui.code(
                        serialize_html(
                            ui.audio(SILENT, autoplay=True, loop=True,
                                     muted=True)
                        ),
                        lang="html",
                    )

            # ── Carte 4 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading('In a card — one episode', level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.heading('Episode 12', level=4)
                            ui.audio(src=SILENT)
                            ui.text("34 min", color="muted", size="sm")

                    ui.heading('Inside a constrained grid cell',
                               level=3)
                    ui.text(
                        'The native player otherwise takes an arbitrary '
                            'width; the root slot sets w-full so it matches '
                            'its column.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 2}, gap="sm"):
                        ui.audio(src=SILENT)
                        ui.audio(src=SILENT)

            # ── Carte 5 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "controls=True by default IS this component's "
                            'accessibility decision, and its only reason to '
                            'exist beside the native tag. With no controls '
                            'there is nothing to tab to and nothing to '
                            'announce: the element is there and nobody can '
                            'play it.',
                        color="muted", size="sm",
                    )
                    ui.text(
                        "The controls rendered are the browser's — "
                            'already labelled, already keyboard-driven, '
                            "already announced in the system's language. That"
                            ' is also the reason not to redraw them: a home-'
                            'made bar would have to reimplement all of that, '
                            'keyboard included, to gain a rounded corner.',
                        color="muted", size="sm",
                    )

                    ui.heading('What the component does NOT provide',
                               level=3)
                    ui.text(
                        'No transcript, and no way to attach one: '
                            'ui.audio is a leaf, it accepts no children, so '
                            'no <track kind="captions"> can get in. An '
                            '<audio> on its own is inaccessible to anyone who'
                            ' cannot hear — the transcript goes BESIDE it, as'
                            ' real text. It is a declared limit, recorded in '
                            '.claude/work/todo.md.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.audio(src=SILENT)
                        ui.text(
                            'Transcript — “Welcome to episode 12. Today, '
                                'typed state.”',
                            color="muted", size="sm",
                        )

            # ── Carte 6 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'Set autoplay to True and check in the emitted '
                            'HTML that muted does NOT appear — that is the '
                            'difference from ui.video.',
                        color="muted", size="sm",
                    )
                    server_panel()
