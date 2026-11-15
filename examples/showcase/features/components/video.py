"""``/video`` — the native player, with captions and a reserved frame."""

from urllib.parse import quote

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("The browser's own player, a poster and a reserved ratio — plus "
           "caption tracks in as many languages as you ship.")

FLOWER = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
POSTER = "https://picsum.photos/id/152/1280/720"


def product_tour() -> None:
    with ui.vstack(gap="sm", classes="w-full max-w-2xl"):
        ui.video(FLOWER, poster=POSTER, ratio="video", controls=True)
        with ui.hstack(justify="between"):
            ui.text("Product tour — planning your first season", weight="medium")
            ui.text("0:05", size="sm", color="muted")


def vtt(*cues: str) -> str:
    """A WebVTT file, inline: one cue every two seconds."""
    body = "WEBVTT\n"
    for i, cue in enumerate(cues):
        body += f"\n00:0{2 * i}.000 --> 00:0{2 * i + 2}.000\n{cue}\n"
    return "data:text/vtt;charset=utf-8," + quote(body)


def captions() -> None:
    with ui.vstack(classes="w-full max-w-2xl"):
        ui.video(FLOWER, poster=POSTER, ratio="video", controls=True, tracks=[
            ui.track(vtt("A bud opens in the morning light.",
                         "Bees arrive within the hour."),
                     srclang="en", label="English", default=True),
            ui.track(vtt("Un bouton s'ouvre à la lumière du matin.",
                         "Les abeilles arrivent dans l'heure."),
                     srclang="fr", label="Français"),
        ])


def ambient() -> None:
    with ui.grid(cols={"base": 1, "md": 2}, gap="lg", classes="w-full items-center"):
        with ui.vstack(gap="sm"):
            ui.text("Greenhouse monitoring", size="sm", color="primary",
                    weight="medium")
            ui.heading("Watch every plant grow, from anywhere", level=3, size="2xl")
            ui.text("Time-lapse cameras in each greenhouse, streamed to one "
                    "dashboard.", color="muted")
        ui.video(FLOWER, poster=POSTER, ratio="square", fit="cover",
                 autoplay=True, loop=True, controls=False)


def clips() -> None:
    with ui.hstack(gap="md", wrap=True, justify="center", align="start"):
        for title in ("Day 1 · seedling", "Day 12 · bloom", "Day 30 · harvest"):
            with ui.vstack(gap="xs", classes="w-40"):
                ui.video(FLOWER, poster=POSTER, ratio="portrait", fit="cover",
                         controls=True, muted=True)
                ui.text(title, size="sm", weight="medium")


def page() -> None:
    page_header(("video", "track"), "Video", SUMMARY)
    example("A product tour", product_tour,
            note="poster= shows a still until play; ratio= keeps the frame's "
                 "place before a single byte of video arrives.")
    example("Captions in two languages", captions, uses=[vtt],
            note="tracks= takes ui.track(...) entries. The browser lists them "
                 "in its CC menu; default=True turns one on.")
    example("An ambient loop", ambient, full=True,
            note="autoplay forces muted — every browser blocks sound that "
                 "starts on its own.")
    example("Vertical clips", clips,
            note="portrait ratio and fit=\"cover\" for phone-shot footage.")
