"""``Video`` test bench.

Sept cartes : Reference / Ratios / La garde autoplay / Edge cases /
Composability / A11y / Server playground. BINDABLE_PROPS = () donc aucune
carte Client.

Périmètre du composant : un <video> natif HABILLÉ, pas un lecteur. Les
contrôles sont ceux du navigateur.

⚠️ AUCUNE source, et pas non plus un chemin bidon : les <video> de cette
page n'ont pas d'attribut src du tout. Un .mp4 dans le dépôt pèserait
pour rien, une URL distante rendrait les probes dépendants du réseau —
et un chemin inexistant, que la v1 de ce banc utilisait, fait tirer des
DIZAINES de 404 au serveur à chaque chargement (constaté dans les logs
de dev). Ce qu'on voit est le poster (un SVG en data:) dans sa boîte au
ratio déclaré : exactement l'état « avant que la vidéo arrive », pour
zéro requête.
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
    """Un poster SVG en data: — déterministe et hors ligne.

    Les # sont échappés : un # non échappé dans une data: URI coupe l'URL
    sur un fragment, et la moitié droite du SVG serait perdue.
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
    """Un fichier WebVTT en data: — même raison que le poster.

    Une piste servie depuis le réseau rendrait le banc dépendant de lui,
    et un chemin inexistant ferait tirer un 404 par piste et par
    chargement. Ici le navigateur charge vraiment la piste : le menu CC
    la liste, et ``textTracks[0].cues.length`` vaut 1.
    """
    body = f"WEBVTT\n\n00:00.000 --> 00:05.000\n{cue}"
    return "data:text/vtt;charset=utf-8," + quote(body)


CAPTION_TRACKS = [
    ui.track(vtt_source("Bienvenue dans Bretzel."),
             srclang="fr", label="Français", default=True),
    ui.track(vtt_source("Welcome to Bretzel."),
             srclang="en", label="English"),
    ui.track(vtt_source("Une page de code sur fond sombre."),
             srclang="fr", label="Audiodescription", kind="descriptions"),
]

POSTER_WIDE = poster_source(480, 270, "#1e293b", "poster 480x270")
POSTER_TALL = poster_source(270, 480, "#4c1d95", "poster 270x480")
# AUCUNE source. Pas « un chemin absent » — pas de src du tout.
#
# La v1 de ce banc pointait ses 16 <video> vers un /media/demo-absente.mp4
# inexistant, en croyant rester « hors ligne ». Résultat, visible dans les
# logs du serveur de dev : des DIZAINES de GET 404 par chargement de page,
# chaque élément réclamant sa source et le navigateur réessayant. Un banc
# ne doit pas marteler le serveur pour démontrer une boîte vide.
#
# Sans src, le composant n'émet pas l'attribut du tout (il ne met JAMAIS
# src="" — un attribut vide se résout contre l'URL du document, donc le
# navigateur retéléchargerait la page comme média). Zéro requête, et le
# poster + la boîte au ratio s'affichent exactement pareil : c'est bien
# l'état « avant que la vidéo arrive » qu'on veut montrer.
SRC = None


class VideoPlayground(PageState):
    """État du banc serveur — un champ par prop + par échappatoire."""

    poster: str = field(default="wide")
    ratio: str = field(default="video")
    fit: str = field(default="contain")
    controls: str = field(default="on")
    autoplay: str = field(default="off")
    loop: str = field(default="off")
    muted: str = field(default="off")
    tracks: str = field(default="off")
    # Échappatoires.
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
        with control("ratio — c'est LUI qui décide de la forme"):
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
            ui.input(value=state.aria_label, placeholder="Démo produit",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.8",
                     on_change=server_changed)
        with control("extra_attrs (un par ligne, clé=valeur)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="preload=none",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Cliquez pour lire",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
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
                "Un <video> natif habillé, pas un lecteur : les contrôles "
                "restent ceux du navigateur. Ce que le composant apporte, "
                "c'est la place réservée (ratio), le poster, et deux "
                "pièges natifs absorbés — autoplay force muted, et "
                "playsinline est toujours émis.",
                color="muted",
            )
            ui.text(
                "Aucune source réelle sur cette page : les chemins .mp4 "
                "sont absents à dessein, pour que le banc reste hors "
                "ligne. Ce que vous voyez est le poster et la boîte — "
                "c'est-à-dire exactement l'état AVANT que la vidéo "
                "arrive.",
                color="muted", size="sm",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading("Avec poster et contrôles (le défaut)",
                               level=3)
                    with ui.vstack(classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video")

                    ui.heading("Sans poster — la boîte sombre", level=3)
                    ui.text(
                        "C'est l'état d'attente : la place est réservée, "
                        "rien ne saute quand la vidéo arrive.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.video(ratio="video")

            # ── Carte 2 — Ratios ────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Ratios", level=2)
                    ui.text(
                        "Le même poster dans les quatre ratios. La forme "
                        "vient du ratio, jamais de la source — même règle "
                        "que ui.image.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Constaté au navigateur : en wide (21/9) dans une "
                        "colonne étroite, la barre de contrôles native "
                        "occupe presque toute la boîte — elle a une "
                        "hauteur minimale que le composant ne peut pas "
                        "réduire. Un ratio très plat va avec une largeur "
                        "généreuse, ou avec controls=False.",
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
                    ui.heading("La garde autoplay", level=2)
                    ui.text(
                        "Tous les navigateurs bloquent une lecture "
                        "automatique avec du son. Sans garde, la vidéo ne "
                        "démarre simplement pas — sans erreur, sans log, "
                        "sans indice visuel. Le composant force donc muted "
                        "dès qu'autoplay est demandé, et l'écrit dans le "
                        "HTML plutôt que de livrer un attribut inerte.",
                        color="muted", size="sm",
                    )
                    ui.heading("autoplay=True, muted non précisé", level=3)
                    ui.text("Le HTML émis porte les deux :",
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
                        "Jamais une prop. Sans lui, iOS sort la vidéo du "
                        "flux et confisque l'écran dès la lecture — "
                        "jamais ce qu'on veut dans une application, et "
                        "c'est le genre de chose qu'on découvre sur un "
                        "iPhone en production.",
                        color="muted", size="sm",
                    )

            # ── Carte 4 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Source absente — la boîte tient", level=3)
                    ui.text(
                        "Toutes les vidéos de cette page sont dans ce "
                        "cas : le ratio a réservé la place, donc rien ne "
                        "bouge.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.video(ratio="video")

                    ui.heading("Poster au ratio contraire", level=3)
                    ui.text(
                        "Un poster 270×480 dans une boîte 16/9. fit="
                        "contain (le défaut) le montre en entier avec du "
                        "letterboxing ; cover le recadrerait — et couper "
                        "l'action est rarement voulu, d'où ce défaut "
                        "inverse de celui d'ui.image.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        for fit in FITS:
                            with ui.vstack(gap="xs"):
                                ui.text(f"fit={fit}", size="xs",
                                        color="muted")
                                ui.video(poster=POSTER_TALL,
                                         ratio="video", fit=fit)

                    ui.heading("Sans contrôles ni autoplay", level=3)
                    ui.text(
                        "Personne ne peut la lire. Le composant ne "
                        "l'interdit pas — c'est une combinaison légitime "
                        "pour une vidéo pilotée par du code — mais elle "
                        "se voit ici.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-xs"):
                        ui.video(controls=False, ratio="video",
                                 poster=POSTER_WIDE)

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading("Dans une carte", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        for label in ("Prise en main", "Nouveautés"):
                            with ui.card():
                                with ui.vstack(gap="sm"):
                                    ui.video(poster=POSTER_WIDE,
                                             ratio="video")
                                    ui.text(label, weight="bold")
                                    ui.text("2 min", color="muted",
                                            size="sm")

                    ui.heading("Dans une cellule de grille contrainte",
                               level=3)
                    with ui.grid(cols={"base": 3}, gap="sm"):
                        for name in ("square", "video", "portrait"):
                            ui.video(poster=POSTER_TALL, ratio=name)

            # ── Carte 6 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "controls=True par défaut, et c'est la décision "
                        "d'accessibilité du composant : le défaut de la "
                        "plateforme est « pas de contrôles », ce qui "
                        "laisse un élément que personne ne peut atteindre "
                        "au clavier. Les contrôles rendus sont ceux du "
                        "navigateur — déjà étiquetés, déjà tabulables, "
                        "déjà annoncés dans la langue du système. Les "
                        "redessiner voudrait dire les réimplémenter, "
                        "clavier compris.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "La garde autoplay a une seconde raison, "
                        "au-delà du blocage navigateur : du son qui part "
                        "seul recouvre la voix d'un lecteur d'écran, et "
                        "l'utilisateur n'a alors plus de moyen simple de "
                        "trouver quoi arrêter.",
                        color="muted", size="sm",
                    )

                    ui.heading("poster n'est pas un texte alternatif",
                               level=3)
                    ui.text(
                        "<video> n'a pas d'attribut alt, et l'affiche "
                        "est une image de plus, décorative. Ce qui "
                        "décrit la vidéo doit vivre À CÔTÉ, en texte "
                        "réel — lisible par tout le monde, y compris "
                        "avant que la vidéo charge.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video")
                        ui.text("Prise en main de Bretzel — 2 min : "
                                "créer une page, brancher un état typé, "
                                "muter.",
                                color="muted", size="sm")

                    ui.heading("Sous-titres — tracks=", level=3)
                    ui.text(
                        "Le composant reste une feuille : les pistes "
                        "sont des DONNÉES, pas des enfants. Un track "
                        "correct veut trois attributs, et ui.track les "
                        "exige tous les trois — une piste sans langue ni "
                        "libellé ne se construit pas, donc elle ne peut "
                        "pas arriver muette dans le menu du navigateur.",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.video(poster=POSTER_WIDE, ratio="video",
                                 tracks=CAPTION_TRACKS)
                    ui.text(
                        "Trois pistes ci-dessus : deux langues de "
                        "sous-titres et une audiodescription. Les "
                        "fichiers sont des data: URI, donc la page "
                        "reste hors ligne — le menu CC du navigateur les "
                        "liste pour de vrai.",
                        color="muted", size="xs",
                    )

                    ui.heading("Ce que le composant ne fournit PAS",
                               level=3)
                    ui.text(
                        "kind=\"metadata\" est refusé : il ne s'adresse "
                        "qu'à du JS (vignettes de survol, marqueurs d'un "
                        "lecteur maison) et ui.video n'est pas un "
                        "lecteur. Pas de sources multiples non plus — un "
                        "seul src, et le jour où plusieurs formats "
                        "remontent, ce sera un sources= sur le modèle de "
                        "tracks=.",
                        color="muted", size="xs",
                    )

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Chaque prop ET chaque échappatoire câblée à un "
                        "contrôle. Mettez autoplay à True et regardez "
                        "muted apparaître dans le HTML émis.",
                        color="muted", size="sm",
                    )
                    server_panel()
