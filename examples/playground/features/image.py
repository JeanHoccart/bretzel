"""``Image`` test bench.

Six visual cards: Reference / Ratios & fit / Edge cases / Composability /
A11y / Server playground. ``BINDABLE_PROPS = ()`` so no Client card —
there is no reactive surface to exercise.

Four props (``src`` / ``alt`` / ``ratio`` / ``fit``), no event.

⚠️ **Every image is an SVG in a ``data:``**, never a remote URL. A bench
that depends on the network makes the Playwright probes intermittent and
makes the suite fail offline — and one would not know whether the red
comes from the component or from DNS. The three sources have different
NATURAL ratios (wide, tall, square): it is what makes the ``cover`` /
``contain`` difference visible to the eye.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/image"

RATIOS = ["square", "video", "portrait", "wide"]
FITS = ["cover", "contain"]


def svg_source(width: int, height: int, fill: str, label: str) -> str:
    """An inline SVG in a data: — a deterministic image source.

    No base64 encoding: an SVG readable in the clear in the HTML is
    debugged by eye, and the URL stays short. The # are escaped because
    an unescaped # in a data: URI cuts the URL on a fragment — the SVG's
    right half would be silently lost.
    """
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' "
        f"height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect width='100%' height='100%' fill='{fill}'/>"
        f"<text x='50%' y='50%' font-family='sans-serif' font-size='24' "
        f"fill='white' text-anchor='middle' dominant-baseline='middle'>"
        f"{label}</text></svg>"
    )
    return "data:image/svg+xml;utf8," + svg.replace("#", "%23")


# Contrasting natural ratios — essential to SEE what fit= does.
WIDE_SRC = svg_source(480, 160, "#2563eb", "480x160")
TALL_SRC = svg_source(160, 480, "#7c3aed", "160x480")
SQUARE_SRC = svg_source(320, 320, "#059669", "320x320")
# A URL that does not exist: shows the themed box stays in place.
BROKEN_SRC = '/static/this-image-does-not-exist.png'


class ImagePlayground(PageState):
    """The server bench's state — one field per prop + per universal
    escape hatch. An empty string means "do not pass the kwarg", so the
    component takes its own default."""

    src: str = field(default="wide")
    alt: str = field(default='A blue rectangle 480 by 160')
    ratio: str = field(default="video")
    fit: str = field(default="cover")
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Modificateurs universels.
    visible: str = field(default="on")
    tooltip: str = field(default="")


SOURCES = {
    "wide": WIDE_SRC,
    "tall": TALL_SRC,
    "square": SQUARE_SRC,
    "broken": BROKEN_SRC,
}


def server_changed(state: ImagePlayground) -> None:
    # A typed param → the dispatcher hydrates the changed control's
    # value into state. server_panel's deps=[ImagePlayground] re-renders
    # it.
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


def build_preview(state: ImagePlayground):
    kwargs: dict = {
        "alt": state.alt,
        "fit": state.fit,
    }
    if state.ratio:
        kwargs["ratio"] = state.ratio
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
    return ui.image(SOURCES.get(state.src, WIDE_SRC), **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[ImagePlayground])
def server_panel() -> None:
    state = ImagePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('src — the SOURCE, not the rendered shape'):
            ui.select(value=state.src,
                      options=[("wide", "source 480×160"),
                               ("tall", "source 160×480"),
                               ("square", "source 320×320"),
                               ("broken", 'Broken URL')],
                      on_change=server_changed)
        with control("alt (obligatoire)"):
            ui.input(value=state.alt, placeholder='Describe the image',
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
        with control("classes"):
            ui.input(value=state.classes, placeholder="rounded-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-image",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Visuel produit",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.5",
                     on_change=server_changed)
        with control('extra_attrs (one per line, key=value)'):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="loading=eager\ndata-test=image",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder='Product photo',
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", 'True (default)'),
                               ("off", 'False (nothing rendered)')],
                      on_change=server_changed)

    ui.divider()

    # The actual call, JUST above the preview. Without this line, one
    # looks at a square image rendered in 16/9 and concludes the
    # component is broken — whereas it is ``ratio`` that commands, and it
    # stayed 30 cm higher up, out of the field of view. The emitted HTML
    # would say so too, but it is folded away behind its toggle.
    natural = {"wide": "480×160", "tall": "160×480",
               "square": "320×320", "broken": 'Broken URL'}
    ui.text(
        f"source {natural.get(state.src, '?')}"
        f" → ratio={state.ratio or 'aucun'}"
        f" · fit={state.fit}",
        size="xs", color="muted",
    )
    if state.ratio and state.src in ("wide", "tall", "square"):
        ui.text(
            'The rendered shape comes from the ratio, never from the '
                'source: change ratio to change the box, fit to choose '
                'between cropping (cover) and showing everything (contain).',
            size="xs", color="muted",
        )

    # Bounded width: without it, an image in ratio="wide" takes the
    # whole card and the box is no longer visible.
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
            ui.heading("Image", level=1)
            ui.text(
                'An image, with its space reserved. ratio= is the real '
                    'contribution: without it the page jumps on load, because'
                    ' every image pushes the content below as it arrives. '
                    'alt= is mandatory — a decorative image is declared '
                    'alt="", explicitly.',
                color="muted",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Balayage visuel de chaque prop.",
                            color="muted", size="sm")

                    ui.heading('With no ratio — natural size', level=3)
                    ui.image(WIDE_SRC, alt="Rectangle bleu 480 par 160")

                    ui.heading('The four ratios', level=3)
                    with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
                        for name in RATIOS:
                            with ui.vstack(gap="xs"):
                                ui.text(name, size="xs", color="muted")
                                ui.image(SQUARE_SRC, alt=f"'Green square, ratio '{name}",
                                         ratio=name)

            # ── Carte 2 — Ratios & fit ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Ratio × fit", level=2)
                    ui.text(
                        'The same source in the same ratio, with both '
                            'fits. cover fills and crops; contain shows '
                            "everything and lets the box's background show at"
                            ' the sides. The difference is only visible if '
                            "the image's natural ratio differs from the "
                            'declared one — hence the 480×160 and 160×480 '
                            'sources.',
                        color="muted", size="sm",
                    )

                    for src, label in ((WIDE_SRC, "source large 480×160"),
                                       (TALL_SRC, "source haute 160×480")):
                        ui.heading(label, level=3)
                        with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                            for fit in FITS:
                                with ui.vstack(gap="xs"):
                                    ui.text(f"ratio=square fit={fit}",
                                            size="xs", color="muted")
                                    ui.image(src,
                                             alt=f"{label}, {fit}",
                                             ratio="square", fit=fit)

            # ── Carte 3 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        'The inputs that break components elsewhere. '
                            'Reproducible live in the server bench further '
                            'down.',
                        color="muted", size="sm",
                    )

                    ui.heading('Broken URL — the box stays', level=3)
                    ui.text(
                        'This is the fallback, and it costs no JS: the '
                            "image's background IS the box. The layout does "
                            'not move, because the ratio reserved the space '
                            'before the request even left.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(BROKEN_SRC,
                                 alt='This image will not load',
                                 ratio="video")

                    ui.heading('empty alt — a decorative image', level=3)
                    ui.text(
                        'alt="" makes the screen reader IGNORE the image.'
                            ' That is not the same as omitting the attribute,'
                            ' which makes it announce the URL.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(SQUARE_SRC, alt="", ratio="square")

                    ui.heading('a very long alt (120 characters)', level=3)
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(BROKEN_SRC, alt="D" * 120, ratio="video")

                    ui.heading('alt with HTML characters (escaping)',
                               level=3)
                    ui.text(
                        'The framework escapes the attribute — the script'
                            ' stays literal text instead of executing.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(SQUARE_SRC,
                                 alt="<script>alert(1)</script>",
                                 ratio="square")

                    ui.heading('An image wider than its parent', level=3)
                    ui.text(
                        'max-w-full on the root slot: it bounds itself to'
                            ' the parent instead of overflowing.',
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-[120px]"):
                        ui.image(WIDE_SRC, alt='Bounded to 120 pixels')

            # ── Carte 4 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text('An image nested inside other components.',
                            color="muted", size="sm")

                    ui.heading('In a ui.card — product thumbnail', level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        for label, src in (("Bleu", WIDE_SRC),
                                           ("Vert", SQUARE_SRC)):
                            with ui.card():
                                with ui.vstack(gap="sm"):
                                    ui.image(src, alt=f"Produit {label}",
                                             ratio="video")
                                    ui.text(label, weight="bold")
                                    ui.text("12,00 €", color="muted",
                                            size="sm")

                    ui.heading('Inside a constrained grid cell',
                               level=3)
                    ui.text(
                        'The case that caught date_picker out: a '
                            'component on its own behaves differently from '
                            'one in a narrow cell.',
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 3}, gap="sm"):
                        for name in ("square", "video", "portrait"):
                            ui.image(TALL_SRC, alt=f"'In a cell, '{name}",
                                     ratio=name)

                    ui.heading('In a ui.tooltip', level=3)
                    with ui.vstack(classes="max-w-xs"):
                        with ui.tooltip('A product visual'):
                            ui.image(SQUARE_SRC, alt="Survolez-moi",
                                     ratio="square")

            # ── Carte 5 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "alt is the repository's ONLY mandatory "
                            'accessibility kwarg. Omitting it is a TypeError '
                            'at call time, not a silently inaccessible render'
                            ' — because a missing alt shows neither on screen'
                            ' nor in HTML skimmed diagonally, only to a '
                            'screen reader.',
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text('alt describes — an informative image',
                                    size="xs", color="muted")
                            ui.image(SQUARE_SRC,
                                     alt="Logo vert de l'application",
                                     ratio="square")
                        with ui.vstack(gap="xs"):
                            ui.text('alt="" — a decorative image, ignored',
                                    size="xs", color="muted")
                            ui.image(WIDE_SRC, alt="", ratio="square")

            # ── Carte 6 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        'The real test bench. Every prop AND every escape'
                            ' hatch is wired to a control; the preview and '
                            'the emitted HTML both refresh on every change.',
                        color="muted", size="sm",
                    )
                    server_panel()
