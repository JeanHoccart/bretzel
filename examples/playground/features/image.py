"""``Image`` test bench.

Six cartes visuelles : Reference / Ratios & fit / Edge cases /
Composability / A11y / Server playground. ``BINDABLE_PROPS = ()`` donc
aucune carte Client — il n'y a pas de surface réactive à exercer.

Quatre props (``src`` / ``alt`` / ``ratio`` / ``fit``), aucun event.

⚠️ **Toutes les images sont des SVG en ``data:``**, jamais une URL
distante. Un banc qui dépend du réseau rend les probes Playwright
intermittents et fait échouer la suite hors ligne — et on ne saurait pas
si le rouge vient du composant ou du DNS. Les trois sources ont des
ratios NATURELS différents (large, haute, carrée) : c'est ce qui rend la
différence ``cover`` / ``contain`` visible à l'œil.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/image"

RATIOS = ["square", "video", "portrait", "wide"]
FITS = ["cover", "contain"]


def svg_source(width: int, height: int, fill: str, label: str) -> str:
    """Un SVG inline en data: — une source d'image déterministe.

    Pas d'encodage base64 : un SVG lisible en clair dans le HTML se
    débogue à l'œil, et l'URL reste courte. Les # sont échappés parce
    qu'un # non échappé dans une data: URI coupe l'URL sur un
    fragment — la moitié droite du SVG serait silencieusement perdue.
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


# Ratios naturels contrastés — indispensable pour VOIR ce que fit= fait.
WIDE_SRC = svg_source(480, 160, "#2563eb", "480x160")
TALL_SRC = svg_source(160, 480, "#7c3aed", "160x480")
SQUARE_SRC = svg_source(320, 320, "#059669", "320x320")
# Une URL qui n'existe pas : montre que la boîte thémée reste en place.
BROKEN_SRC = "/static/cette-image-nexiste-pas.png"


class ImagePlayground(PageState):
    """État du banc serveur — un champ par prop + par échappatoire
    universelle. Une chaîne vide veut dire « ne passe pas le kwarg »,
    pour que le composant prenne son propre défaut."""

    src: str = field(default="wide")
    alt: str = field(default="Un rectangle bleu de 480 par 160")
    ratio: str = field(default="video")
    fit: str = field(default="cover")
    # Échappatoires.
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
    # Param typé → le dispatcher hydrate la valeur du contrôle modifié
    # dans state. Le deps=[ImagePlayground] de server_panel
    # le re-rend.
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
        with control("src — la SOURCE, pas la forme rendue"):
            ui.select(value=state.src,
                      options=[("wide", "source 480×160"),
                               ("tall", "source 160×480"),
                               ("square", "source 320×320"),
                               ("broken", "URL cassée")],
                      on_change=server_changed)
        with control("alt (obligatoire)"):
            ui.input(value=state.alt, placeholder="Décris l'image",
                     on_change=server_changed)
        with control("ratio — c'est LUI qui décide de la forme"):
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
        with control("extra_attrs (un par ligne, clé=valeur)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="loading=eager\ndata-test=image",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Photo du produit",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
                      on_change=server_changed)

    ui.divider()

    # L'appel effectif, JUSTE au-dessus de l'aperçu. Sans cette ligne, on
    # regarde une image carrée rendue en 16/9 et on conclut que le
    # composant est cassé — alors que c'est ``ratio`` qui commande, et
    # qu'il est resté 30 cm plus haut, hors du champ de vision. Le HTML
    # émis le dirait aussi, mais il est replié derrière son toggle.
    natural = {"wide": "480×160", "tall": "160×480",
               "square": "320×320", "broken": "URL cassée"}
    ui.text(
        f"source {natural.get(state.src, '?')}"
        f" → ratio={state.ratio or 'aucun'}"
        f" · fit={state.fit}",
        size="xs", color="muted",
    )
    if state.ratio and state.src in ("wide", "tall", "square"):
        ui.text(
            "La forme rendue vient du ratio, jamais de la source : "
            "changez ratio pour changer la boîte, fit pour choisir "
            "entre recadrer (cover) et tout montrer (contain).",
            size="xs", color="muted",
        )

    # Largeur bornée : sans ça, une image en ratio="wide" occupe toute
    # la carte et on ne voit plus la boîte.
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
                "Une image, avec sa place réservée. ratio= est le "
                "vrai apport : sans lui la page saute au chargement, "
                "parce que chaque image pousse le contenu d'en dessous "
                "en arrivant. alt= est obligatoire — une image "
                "décorative se déclare alt=\"\", explicitement.",
                color="muted",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Balayage visuel de chaque prop.",
                            color="muted", size="sm")

                    ui.heading("Sans ratio — taille naturelle", level=3)
                    ui.image(WIDE_SRC, alt="Rectangle bleu 480 par 160")

                    ui.heading("Les quatre ratios", level=3)
                    with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
                        for name in RATIOS:
                            with ui.vstack(gap="xs"):
                                ui.text(name, size="xs", color="muted")
                                ui.image(SQUARE_SRC, alt=f"Carré vert, "
                                                         f"ratio {name}",
                                         ratio=name)

            # ── Carte 2 — Ratios & fit ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Ratio × fit", level=2)
                    ui.text(
                        "La même source dans le même ratio, avec les "
                        "deux fit. cover remplit et recadre ; "
                        "contain montre tout et laisse voir le fond "
                        "de la boîte sur les côtés. La différence n'est "
                        "visible que si le ratio naturel de l'image "
                        "diffère du ratio déclaré — d'où les sources "
                        "480×160 et 160×480.",
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
                        "Les entrées qui cassent des composants "
                        "ailleurs. Reproductibles en direct dans le banc "
                        "serveur plus bas.",
                        color="muted", size="sm",
                    )

                    ui.heading("URL cassée — la boîte reste", level=3)
                    ui.text(
                        "C'est le fallback, et il ne coûte aucun JS : le "
                        "fond de l'image EST la boîte. La mise en page "
                        "ne bouge pas, parce que le ratio a réservé la "
                        "place avant même la requête.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(BROKEN_SRC,
                                 alt="Cette image ne se chargera pas",
                                 ratio="video")

                    ui.heading("alt vide — image décorative", level=3)
                    ui.text(
                        "alt=\"\" fait IGNORER l'image par le "
                        "lecteur d'écran. Ce n'est pas la même chose "
                        "qu'omettre l'attribut, qui fait annoncer l'URL.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(SQUARE_SRC, alt="", ratio="square")

                    ui.heading("alt très long (120 caractères)", level=3)
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(BROKEN_SRC, alt="D" * 120, ratio="video")

                    ui.heading("alt avec caractères HTML (échappement)",
                               level=3)
                    ui.text(
                        "Le framework échappe l'attribut — le script "
                        "reste du texte littéral au lieu de s'exécuter.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.image(SQUARE_SRC,
                                 alt="<script>alert(1)</script>",
                                 ratio="square")

                    ui.heading("Image plus large que son parent", level=3)
                    ui.text(
                        "max-w-full au slot racine : elle se borne "
                        "au parent au lieu de déborder.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-[120px]"):
                        ui.image(WIDE_SRC, alt="Bornée à 120 pixels")

            # ── Carte 4 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Image imbriquée dans d'autres composants.",
                            color="muted", size="sm")

                    ui.heading("Dans ui.card — vignette produit", level=3)
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

                    ui.heading("Dans une cellule de grille contrainte",
                               level=3)
                    ui.text(
                        "Le cas qui a piégé date_picker : un composant "
                        "seul se comporte autrement qu'en cellule "
                        "étroite.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 3}, gap="sm"):
                        for name in ("square", "video", "portrait"):
                            ui.image(TALL_SRC, alt=f"En cellule, {name}",
                                     ratio=name)

                    ui.heading("Dans ui.tooltip", level=3)
                    with ui.vstack(classes="max-w-xs"):
                        with ui.tooltip("Un visuel produit"):
                            ui.image(SQUARE_SRC, alt="Survolez-moi",
                                     ratio="square")

            # ── Carte 5 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "alt est le SEUL kwarg d'accessibilité "
                        "obligatoire du dépôt. L'omettre est une "
                        "TypeError à l'appel, pas un rendu "
                        "silencieusement inaccessible — parce qu'un alt "
                        "manquant ne se voit ni à l'écran ni dans le "
                        "HTML relu en diagonale, seulement au lecteur "
                        "d'écran.",
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("alt décrit — image informative",
                                    size="xs", color="muted")
                            ui.image(SQUARE_SRC,
                                     alt="Logo vert de l'application",
                                     ratio="square")
                        with ui.vstack(gap="xs"):
                            ui.text('alt="" — image décorative, ignorée',
                                    size="xs", color="muted")
                            ui.image(WIDE_SRC, alt="", ratio="square")

            # ── Carte 6 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Le vrai banc d'essai. Chaque prop ET chaque "
                        "échappatoire est câblée à un contrôle ; "
                        "l'aperçu et le HTML émis se rafraîchissent à "
                        "chaque changement.",
                        color="muted", size="sm",
                    )
                    server_panel()
