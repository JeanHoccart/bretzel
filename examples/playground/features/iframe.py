"""``IFrame`` test bench.

Sept cartes : le sandbox / title & ratio / Reference / Composability /
Edge cases / A11y / Server playground. ``BINDABLE_PROPS = ()`` et
``EVENTS = ()`` donc aucune carte Client ni événement.

La seule vraie question du composant est son **sandbox par défaut** : la
carte 1 lui est entièrement consacrée.

⚠️ Hors ligne intégralement — les cadres utilisent ``srcdoc`` (document
inline, zéro requête réseau). C'est la leçon du banc vidéo : un chemin
bidon n'est pas « rester hors ligne », c'est un 404 par élément.
"""

from bretzel import refreshable, ui
from bretzel.components import SANDBOX_BASELINE
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/iframe"

RATIOS = ["square", "video", "portrait", "wide"]


def doc(body: str, bg: str = "#f8fafc") -> str:
    """Un document inline pour ``srcdoc`` — aucune requête réseau."""
    return (
        f"<body style=\"margin:0;background:{bg};font-family:sans-serif;"
        f"display:flex;align-items:center;justify-content:center;"
        f"height:100vh;color:#0f172a\">{body}</body>"
    )


DOC_MAP = doc("<strong>Une carte irait ici</strong>", "#e0f2fe")
DOC_FORM = doc("<em>Un widget de paiement irait ici</em>", "#fef3c7")
DOC_PLAIN = doc("Document embarqué")


class EmbedPlayground(PageState):
    """État du banc serveur — iframe uniquement (l'audio n'a pas assez de
    surface pour mériter un panneau)."""

    ratio: str = field(default="video")
    title: str = field(default="Document de démonstration")
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
            ui.input(value=state.title, placeholder="Décris le cadre",
                     on_change=server_changed)
        with control("ratio"):
            ui.select(value=state.ratio,
                      options=[("", "aucun")] + [(r, r) for r in RATIOS],
                      on_change=server_changed)
        with control("sandbox"):
            ui.select(value=state.sandbox_mode,
                      options=[("baseline", "défaut (base Bretzel)"),
                               ("custom", "liste explicite"),
                               ("maximal", 'sandbox="" — tout refusé'),
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
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
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
                "Un document tiers, borné par défaut. La seule vraie "
                "question du composant est son sandbox — Bretzel en pose "
                "un même quand vous n'en demandez pas, et la carte "
                "ci-dessous explique lequel et pourquoi.",
                color="muted",
            )
            ui.text(
                "Page entièrement hors ligne : les cadres utilisent "
                "srcdoc, un document inline, donc zéro requête réseau.",
                color="muted", size="sm",
            )

            # ── Carte 1 — IFrame : le sandbox ───────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Le sandbox par défaut", level=2)
                    ui.text(
                        "Bretzel pose un sandbox même quand vous n'en "
                        "demandez pas. Le point n'est pas ce que la liste "
                        "autorise, c'est ce qu'elle TAIT : dès qu'un "
                        "attribut sandbox existe, la navigation du haut "
                        "de page et les téléchargements sont refusés tant "
                        "qu'on ne les réclame pas. Ce sont les deux "
                        "vecteurs qui transforment un embed en "
                        "hameçonnage.",
                        color="muted", size="sm",
                    )
                    ui.code(SANDBOX_BASELINE, lang="text")
                    ui.text(
                        "Les quatre permissions accordées sont celles "
                        "sans lesquelles une carte, un lecteur ou un "
                        "widget de paiement ne marchent pas du tout. Un "
                        "défaut que tout le monde désactive au premier "
                        "essai n'apprendrait qu'une chose : à le "
                        "désactiver.",
                        color="muted", size="sm",
                    )

                    ui.heading("Les trois sorties, toutes explicites",
                               level=3)
                    with ui.vstack(gap="sm"):
                        ui.code(
                            'ui.iframe(src, title="…", '
                            'sandbox="allow-scripts")  # votre liste\n'
                            'ui.iframe(src, title="…", '
                            'sandbox="")               # tout refusé\n'
                            'ui.iframe(src, title="…", '
                            'sandbox=None)             # aucune restriction',
                            lang="python",
                        )

            # ── Carte 2 — IFrame : title et ratio ───────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("title et ratio", level=2)
                    ui.text(
                        "title est obligatoire : un lecteur d'écran "
                        "annonce les cadres par leur titre, et sans lui "
                        "l'utilisateur entend « cadre » sans savoir si "
                        "c'est une carte ou un formulaire de paiement. "
                        "Même raison que l'alt d'ui.image — l'oubli est "
                        "invisible à l'écran.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "ratio réserve la hauteur. Un embed est la "
                        "première cause de saut de page, et un iframe "
                        "sans dimensions retombe sur un 300×150 hérité "
                        "des années 90.",
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ratio=video", size="xs", color="muted")
                            ui.iframe(title="Carte de démonstration",
                                      ratio="video",
                                      attrs={"srcdoc": DOC_MAP})
                        with ui.vstack(gap="xs"):
                            ui.text("ratio=square", size="xs", color="muted")
                            ui.iframe(title="Paiement de démonstration",
                                      ratio="square",
                                      attrs={"srcdoc": DOC_FORM})

            # ── Carte 3 — Surface d'API ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text(
                        "Chaque paramètre du composant, en appel "
                        "littéral — c'est ce que la gate "
                        "test_playground_demos_the_api vérifie.",
                        color="muted", size="sm",
                    )

                    ui.heading("ui.iframe — tous les paramètres", level=3)
                    with ui.vstack(classes="max-w-md", gap="sm"):
                        ui.iframe(
                            src="data:text/html,<p>src explicite</p>",
                            title="Cadre avec src, ratio et sandbox",
                            ratio="wide",
                            sandbox="allow-scripts",
                        )

                    ui.heading("Les quatre ratios", level=3)
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

                    ui.heading("Sans ratio — le 300×150 des années 90",
                               level=3)
                    ui.text(
                        "C'est le défaut natif, et il ne dépend ni du "
                        "contenu ni du conteneur. Il est ici pour être "
                        "reconnu : une hauteur qui ne ressemble à rien "
                        "de ce qu'on a demandé, c'est un ratio oublié.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(title="Cadre sans ratio",
                                  attrs={"srcdoc": DOC_PLAIN})

                    ui.heading("Les trois sorties du sandbox, rendues",
                               level=3)
                    ui.text(
                        "sandbox=\"\" refuse TOUT : un document statique "
                        "s'affiche encore, un script n'y tournerait "
                        "plus. sandbox=None retire l'attribut, donc "
                        "toute restriction avec lui — le cadre redevient "
                        "un pair de la page.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("défaut (base Bretzel)", size="xs",
                                    color="muted")
                            ui.iframe(title="Cadre par défaut",
                                      ratio="square",
                                      attrs={"srcdoc": DOC_PLAIN})
                        with ui.vstack(gap="xs"):
                            ui.text('sandbox="" — tout refusé', size="xs",
                                    color="muted")
                            ui.iframe(title="Cadre verrouillé",
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
                        "Le cadre reste vide, mais il GARDE sa boîte : "
                        "c'est tout l'intérêt du ratio, la page ne "
                        "sautera pas quand la source arrivera — ou "
                        "n'arrivera pas.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(src="/cette-route-n-existe-pas",
                                  title="Cadre dont la source échoue",
                                  ratio="video")

                    ui.heading("Titre très long", level=3)
                    ui.text(
                        "Le titre n'est pas rendu à l'écran : il peut "
                        "être long sans rien déplacer. C'est aussi "
                        "pourquoi son absence est invisible.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-md"):
                        ui.iframe(
                            title=(
                                "Tableau de bord des ventes du "
                                "quatrième trimestre, filtré sur la "
                                "région Grand Est, mis à jour toutes "
                                "les quinze minutes"
                            ),
                            ratio="video",
                            attrs={"srcdoc": DOC_MAP},
                        )

            # ── Carte 5 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading("Dans une cellule de grille contrainte",
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
                        "title est le SEUL paramètre obligatoire du "
                        "composant, et c'est une décision "
                        "d'accessibilité : un lecteur d'écran annonce "
                        "les cadres par leur titre, donc sans lui "
                        "l'utilisateur entend « cadre » sans savoir si "
                        "c'est une carte ou un formulaire de paiement. "
                        "Comme l'alt d'une image, l'oubli ne se voit "
                        "pas à l'écran — d'où le refus au construct "
                        "plutôt qu'un défaut vide.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Un titre n'est utile que s'il DISTINGUE. "
                        "« Cadre » ou « Contenu embarqué » satisfont le "
                        "constructeur et n'apprennent rien : la question "
                        "à laquelle il répond est « dois-je entrer "
                        "là-dedans ? ».",
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

                    ui.heading("Le cadre est un DOCUMENT, pas un widget",
                               level=3)
                    ui.text(
                        "Le focus y entre au Tab et continue à "
                        "l'intérieur : ce qui s'y trouve échappe "
                        "entièrement au thème, aux directives et aux "
                        "gates de Bretzel. Un embed tiers peut piéger "
                        "le clavier sans que rien ici ne le sache — "
                        "c'est aussi ce que le sandbox par défaut "
                        "limite.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "ratio a lui aussi sa part : un cadre qui "
                        "grandit après coup décale ce qu'on visait. "
                        "Pour qui pointe difficilement, un bouton qui "
                        "bouge n'est pas un défaut d'esthétique.",
                        color="muted", size="sm",
                    )

            # ── Carte 7 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Changez le mode sandbox et regardez l'attribut "
                        "apparaître, changer, ou disparaître dans le HTML "
                        "émis.",
                        color="muted", size="sm",
                    )
                    server_panel()
