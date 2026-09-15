"""``Html`` test bench — la porte de sortie.

Six cartes : Reference / Ce que ça débloque / Sécurité / Edge cases /
Composability / Server playground. ``BINDABLE_PROPS = ()`` donc aucune
carte Client — et le constructeur REJETTE un ``ClientBinding``, ce que
la carte Sécurité montre.

Une seule prop (``content``), aucun event.

⚠️ Tous les exemples sont **hors ligne** : SVG inline, ``<iframe srcdoc>``,
``<video>`` / ``<audio>`` sans source distante. Un banc qui dépend du
réseau rend les probes intermittents et on ne sait plus si le rouge vient
du composant ou du DNS.

⚠️ Aucune carte n'injecte de ``<script>`` réel. Le danger se DÉCRIT et se
démontre par contraste avec ``ui.markdown`` ; l'exécuter dans une page de
démo salirait la console et donnerait le mauvais exemple.
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
    "<iframe title='Document embarqué' width='100%' height='120' "
    "style='border:1px solid rgba(128,128,128,.4);border-radius:8px' "
    "srcdoc=\"<p style='font-family:sans-serif;padding:12px'>"
    "Je suis un document dans un iframe.</p>\"></iframe>"
)

VIDEO_SNIPPET = (
    "<video controls width='260' "
    "style='border-radius:8px;background:#111'></video>"
)

AUDIO_SNIPPET = "<audio controls></audio>"

TABLE_SNIPPET = (
    "<table style='border-collapse:collapse'>"
    "<tr><th style='border:1px solid rgba(128,128,128,.4);padding:4px 10px'>"
    "Clé</th>"
    "<th style='border:1px solid rgba(128,128,128,.4);padding:4px 10px'>"
    "Valeur</th></tr>"
    "<tr><td style='border:1px solid rgba(128,128,128,.4);padding:4px 10px'>"
    "region</td>"
    "<td style='border:1px solid rgba(128,128,128,.4);padding:4px 10px'>"
    "eu-west-3</td></tr></table>"
)


class HtmlPlayground(PageState):
    """État du banc serveur — un champ par prop + par échappatoire."""

    content: str = field(default="<b>Du HTML</b> écrit à la main.")
    tag: str = field(default="div")
    # Échappatoires.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Modificateurs universels.
    visible: str = field(default="on")
    tooltip: str = field(default="")


def server_changed(state: HtmlPlayground) -> None:
    # Param typé → le dispatcher hydrate la valeur du contrôle modifié.
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
        with control("content — injecté VERBATIM"):
            ui.textarea(value=state.content, rows=4,
                        placeholder="<b>gras</b>",
                        on_change=server_changed)
        with control("tag (kwarg universel)"):
            ui.select(value=state.tag,
                      options=[("div", "div (défaut)"), ("span", "span"),
                               ("section", "section"), ("figure", "figure")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="text-sm italic",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-embed",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Contenu embarqué",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.8",
                     on_change=server_changed)
        with control("extra_attrs (un par ligne, clé=valeur)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=embed",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Contenu tiers",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
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
                "La porte de sortie : injecter du balisage que le "
                "framework n'a pas produit. Le nœud sous-jacent existait "
                "depuis le début et servait déjà quatre composants ; il "
                "n'était simplement pas ouvert au code applicatif. "
                "C'est un puits à XSS — le contenu doit être un littéral "
                "que vous avez écrit, ou une valeur passée par un "
                "assainisseur juste avant.",
                color="muted",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Le contenu sort verbatim, jamais échappé.",
                            color="muted", size="sm")

                    ui.heading("Balisage simple", level=3)
                    ui.html("<b>gras</b>, <i>italique</i>, "
                            "<code>du code</code>, et un "
                            "<a href='#top'>lien</a>.")

                    ui.heading("tag= change l'enveloppe", level=3)
                    ui.text(
                        "L'enveloppe existe pour que les kwargs "
                        "universels aient où atterrir. tag= la choisit ; "
                        "rien ne la supprime.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="sm"):
                        ui.text("En ligne :")
                        ui.html("<b>dans un span</b>", tag="span")

                    ui.heading("classes= s'ajoute au marqueur", level=3)
                    ui.html("<span>Petit et italique.</span>",
                            classes="text-sm italic")

            # ── Carte 2 — Ce que ça débloque ────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Quand l'utiliser — et quand NON", level=2)
                    ui.text(
                        "Cette page a d'abord démontré la porte de sortie "
                        "avec une vidéo, un audio et un iframe. Deux jours "
                        "plus tard ui.video, ui.audio et ui.iframe "
                        "existaient, et la démonstration enseignait le "
                        "contraire de ce qu'il faut faire. Elle est "
                        "corrigée ici — mais la leçon vaut d'être écrite : "
                        "une page qui explique une API vieillit avec elle.",
                        color="muted", size="sm",
                    )

                    ui.heading("Ce qui a désormais son composant", level=3)
                    ui.text(
                        "Vidéo, audio, cadre embarqué et image ne passent "
                        "PLUS par ici. Leurs composants portent ce qu'un "
                        "ui.html ne portera jamais : une place réservée "
                        "(ratio), un alt ou un title obligatoire, un "
                        "sandbox par défaut, et la garde autoplay→muted.",
                        color="muted", size="xs",
                    )
                    ui.code(
                        "ui.video(src, poster=..., ratio='video')\n"
                        "ui.audio(src)\n"
                        "ui.iframe(src, title='...', ratio='video')\n"
                        "ui.image(src, alt='...', ratio='square')",
                        lang="python",
                    )

                    ui.heading("Ce qui reste à la porte de sortie", level=3)
                    ui.text(
                        "Le balisage qu'aucun composant ne couvre — et "
                        "aucun ne le mérite tant qu'un seul usage le "
                        "réclame.",
                        color="muted", size="xs",
                    )
                    ui.html(
                        "<details style='padding:8px 0'>"
                        "<summary>Un &lt;details&gt; natif</summary>"
                        "<p style='margin:8px 0 0'>Aucun composant Bretzel "
                        "ne rend cette balise.</p></details>"
                    )

                    ui.heading("SVG inline", level=3)
                    ui.text(
                        "Pour une image, préférez ui.image — il réserve "
                        "la place et impose un alt. Le SVG inline est "
                        "pour ce qu'une balise img ne peut pas faire : "
                        "styler ou animer l'intérieur du dessin.",
                        color="muted", size="xs",
                    )
                    ui.html(SVG_SNIPPET)

            # ── Carte 3 — Sécurité ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Sécurité", level=2)
                    ui.text(
                        "Tout ce qui entre sort dans la page. Une chaîne "
                        "venue d'un utilisateur et injectée ici s'exécute. "
                        "Cette page n'en fait pas la démonstration — un "
                        "script réel dans une page de démo salit la "
                        "console et donne le mauvais exemple — mais le "
                        "contraste ci-dessous dit exactement ce qui "
                        "change.",
                        color="muted", size="sm",
                    )

                    ui.heading("Le même texte, deux composants", level=3)
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ui.markdown — échappé, donc sûr",
                                    size="xs", color="muted")
                            ui.markdown("<b>Ce gras reste du texte.</b>")
                        with ui.vstack(gap="xs"):
                            ui.text("ui.html — interprété, donc à vous "
                                    "de garantir la source",
                                    size="xs", color="muted")
                            ui.html("<b>Ce gras est du gras.</b>")

                    ui.heading("Ce que le constructeur refuse", level=3)
                    ui.text(
                        "Un ClientBinding lève : faire écrire du balisage "
                        "au runtime depuis l'état client serait un puits "
                        "à XSS piloté par le client, et le serveur ne "
                        "garantirait plus rien. Pour du HTML qui change, "
                        "gardez la source dans un PageState et re-rendez "
                        "la zone — le serveur reste l'auteur du balisage. "
                        "Un Component lève aussi : content est une string "
                        "de balisage, pas un slot.",
                        color="muted", size="sm",
                    )

                    ui.heading("Et la gate", level=3)
                    ui.text(
                        "Les appels à ui.html de ce dépôt sont une liste "
                        "fermée, vérifiée par "
                        "tests/consistency/test_ui_html_call_sites_are_listed.py. "
                        "En ajouter un fait rougir la suite — c'est ça qui "
                        "rend chaque injection auditable, pas le nom du "
                        "composant.",
                        color="muted", size="sm",
                    )

            # ── Carte 4 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Contenu vide", level=3)
                    ui.text(
                        "L'enveloppe est rendue quand même : les kwargs "
                        "universels (id, classes, attrs) doivent avoir un "
                        "porteur, même sans contenu.",
                        color="muted", size="xs",
                    )
                    ui.html("")

                    ui.heading("HTML mal formé", level=3)
                    ui.text(
                        "Le framework ne parse pas, ne répare pas, ne "
                        "valide pas. Le navigateur fait ce qu'il fait "
                        "d'habitude — ici il ferme la balise pour vous.",
                        color="muted", size="xs",
                    )
                    ui.html("<b>ouverte sans fermeture")

                    ui.heading("Contenu volumineux", level=3)
                    ui.html(TABLE_SNIPPET)

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Le composant se compose comme n'importe quel "
                        "autre — c'est son CONTENU qui échappe au "
                        "framework, pas lui.",
                        color="muted", size="sm",
                    )

                    ui.heading("Dans une carte, entre des composants",
                               level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.heading("Rapport", level=4)
                            ui.text("Résumé généré côté serveur :",
                                    color="muted", size="sm")
                            ui.html(TABLE_SNIPPET)
                            with ui.hstack():
                                ui.badge("brouillon", color="warning")
                                ui.button("Publier", color="primary")

                    ui.heading("Dans une cellule de grille contrainte",
                               level=3)
                    with ui.grid(cols={"base": 2}, gap="md"):
                        ui.html(SVG_SNIPPET)
                        ui.html(TABLE_SNIPPET)

            # ── Carte 6 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "C'est le seul composant du catalogue dont "
                        "l'accessibilité n'est PAS garantie, et il faut "
                        "le dire franchement : le framework ne parse pas "
                        "le fragment, donc il ne peut rien en vérifier. "
                        "Un <img> sans alt, un niveau de titre sauté, un "
                        "<div> dans un <p> passent verbatim — et aucune "
                        "gate ne pourra jamais les voir, puisque le "
                        "contenu n'existe qu'à l'exécution.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Ailleurs, Bretzel porte cette charge à votre "
                        "place : ui.iframe REFUSE de se construire sans "
                        "title, ui.form_field relie son label à son "
                        "contrôle. Ici la charge revient à l'auteur du "
                        "fragment — c'est le prix de la porte de sortie, "
                        "pas un oubli.",
                        color="muted", size="sm",
                    )

                    ui.heading("Le même tableau, deux fois", level=3)
                    ui.text(
                        "À gauche, aucune structure : un lecteur d'écran "
                        "annonce six cellules sans dire de quoi elles "
                        "sont la colonne. À droite, un <th scope=\"col\"> "
                        "et une légende — le même rendu visuel, une "
                        "lecture qui a du sens.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        ui.html(
                            "<table><tr><td>Produit</td>"
                            "<td>Stock</td></tr>"
                            "<tr><td>Câble</td><td>12</td></tr></table>"
                        )
                        ui.html(
                            "<table><caption>Stock par produit</caption>"
                            "<thead><tr>"
                            "<th scope=\"col\">Produit</th>"
                            "<th scope=\"col\">Stock</th></tr></thead>"
                            "<tbody><tr><td>Câble</td>"
                            "<td>12</td></tr></tbody></table>"
                        )

                    ui.heading("tag= évite une enveloppe illégale",
                               level=3)
                    ui.text(
                        "L'enveloppe par défaut est un <div> neutre : "
                        "aucun rôle, donc elle n'ajoute ni ne retire de "
                        "sémantique. Mais un <div> entre un <ul> et ses "
                        "<li> casse la liste pour le lecteur d'écran — "
                        "tag=\"ul\" met l'enveloppe À LA PLACE du "
                        "parent au lieu de s'intercaler.",
                        color="muted", size="xs",
                    )
                    ui.html("<li>premier</li><li>second</li>", tag="ul")

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Tapez du HTML dans le champ content : il part "
                        "verbatim dans la page. Le HTML émis en dessous "
                        "montre l'enveloppe que le composant ajoute.",
                        color="muted", size="sm",
                    )
                    server_panel()
