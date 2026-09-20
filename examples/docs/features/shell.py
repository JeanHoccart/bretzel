"""``shell`` — le cadre racine de la doc, exposé comme une FEATURE.

Un « layout » n'est pas un concept spécial : c'est une feature qui dessine
le chrome (ici la sidebar) et expose une région via ``ui.outlet()``.
Décorée ``@layout`` ici même — aucune wiring centrale, aucun ``app/``.

``NAV`` vit ici (la feature qui la rend). ``features/stubs.py`` la relit
pour générer les chapitres pas encore écrits. Un seul propriétaire. Dans
le modèle metadata visé (déféré), ces entrées seraient dérivées du
placement de chaque feature — pour l'instant on reste en références de code.
"""

from __future__ import annotations

from functools import partial

from bretzel import Language, Screen, layout, ui
from bretzel.state import ClientState, field
from bretzel.theme import ColorScheme
from examples.docs.lib.i18n import tr

#: Les trois modes, dans l'ordre où on les lit. MÊME tuple que
#: ``examples/playground/app/layout.py`` — les deux coques se lisent l'une
#: après l'autre, et une entrée qui diffère se lit comme une différence de
#: FRAMEWORK alors que ce n'en est pas une.
#:
#: Trois entrées et non un bascule : ``system`` est un état à part entière
#: — « suis mon OS » — qu'un contrôle à deux positions ne sait pas
#: exprimer. On choisit, on ne devine pas dans quel sens ça va basculer.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", tr('Light theme',
                 'Thème clair'), "sun"),
    ("dark", tr('Dark theme',
                'Thème sombre'), "moon"),
    ("system", tr('System theme',
                  'Thème système'), "monitor"),
)


class DocsNavigation(ClientState):
    """Recherche locale dans le sommaire, sans requête serveur."""

    query: str = field(default="")

# (section, [(label, href, icon, blurb)]) — le blurb ne sert QU'au stub
# d'un chapitre pas encore écrit ; il ne décide plus de rien (cf.
# ``stubs.py``, qui dérive la livraison de la marque ``@page``).
#
# LES CINQ SECTIONS, ET POURQUOI CELLES-LÀ (refondu le 2026-09-03)
# ================================================================
# Il y a TROIS natures de page, et l'ancienne nav n'en montrait aucune :
# ce qu'on lit UNE FOIS dans l'ordre, ce qu'on ouvre QUAND on a le
# problème, et ce qu'on CONSULTE. Les deux dernières vivaient dans un
# même sac de onze entrées — plus lourd à lui seul que tout le fil
# d'apprentissage (neuf).
#
# D'où :
#
#   DÉMARRER    le fil, dans l'ordre, une fois. ``/config`` y est REMONTÉ
#               du fond de l'ancienne référence : on n'essaie rien sans
#               savoir lancer.
#   LE CYCLE    le cœur. Trois piliers × deux côtés. C'était trois
#               sections de deux entrées ; la grille était donc COUPÉE en
#               trois alors que c'est UNE idée — « les deux moitiés » de
#               ``/how``. Un seul titre, six lignes, et la symétrie se
#               voit.
#   CONSTRUIRE  ce qu'on ouvre en montant une vraie app.
#   LES SUJETS  un mécanisme, un chapitre. C'est ici que viendront les
#               sept manquants (listes, glisser-déposer, graphiques,
#               temps réel, langues, auth, défilement gelé) — la dette
#               est tenue par ``test_a_capability_is_anchored``.
#   CHERCHER    les INDEX, générés d'une source unique. On n'y apprend
#               pas : ils listent et renvoient (cf. la règle en tête de
#               ``examples/docs/main.py``).
NAV = [
    (tr('GET STARTED',
        'DÉMARRER'), [
        ("Introduction", "/", "compass", ""),
        (tr('Get started in 5 minutes',
            'Démarrer en 5 minutes'), "/quickstart", "rocket", ""),
        ("Comprendre Bretzel", "/how", "book-open", ""),
        (tr('Describe the UI',
            "Décrire l'UI"), "/describe", "layout-template", ""),
        # Le jumeau du précédent : l'un dit ce qui existe, l'autre juge ce
        # qu'on en a fait. Ils se lisent l'un après l'autre.
        (tr('Judge the code',
            'Juger le code'), "/check", "shield-check", ""),
    ]),
    (tr('THE CYCLE',
        'LE CYCLE'), [
        (tr('State · server',
            'État · serveur'), "/state-server", "database", ""),
        (tr('State · client',
            'État · client'), "/state-client", "monitor", ""),
        ("Actions · serveur", "/actions-server", "mouse-pointer-click", ""),
        ("Actions · client", "/actions-client", "terminal", ""),
        (tr('Reactivity · server',
            'Réactivité · serveur'), "/reactivity-server", "zap", ""),
        (tr('Reactivity · client',
            'Réactivité · client'), "/reactivity-client", "activity", ""),
    ]),
    ("CONSTRUIRE", [
        ("Structure d'app", "/structure", "layers", ""),
        ("Carte de l'app", "/app-map", "network", ""),
        (tr('Theme',
            'Thème'), "/theme", "palette", ""),
    ]),
    (tr('THE SUBJECTS',
        'LES SUJETS'), [
        # ⚠️ Renommé le 2026-09-03. Il s'appelait « Capacités
        # navigateur », voisin immédiat de « Ce que Bretzel sait faire » :
        # deux entrées dont les noms se confondaient alors qu'elles ne
        # font pas le même métier — l'une enseigne, l'autre indexe.
        #
        # Les sept suivants sont arrivés le 2026-09-03 : la section
        # n'avait que deux entrées alors que HUIT capacités n'avaient
        # aucun chapitre. Le cliquet de `test_a_capability_is_anchored`
        # tombe donc de 8 à 0. `/lists` en couvre deux — la liste et le
        # tableau sont le même besoin à deux échelles.
        ("Listes et tableaux", "/lists", "table", ""),
        ("Formulaires", "/forms", "clipboard-list", ""),
        (tr('Drag and drop',
            'Glisser-déposer'), "/drag", "move", ""),
        ("Graphiques", "/charts", "chart-line", ""),
        (tr('The cadence',
            'La cadence'), "/cadence", "timer", ""),
        (tr('Scrolling',
            'Le défilement'), "/scrolling", "scroll", ""),
        (tr('The languages',
            'Les langues'), "/languages", "languages", ""),
        ("Authentification", "/auth", "key-round", ""),
        (tr('The browser',
            'Le navigateur'), "/browser", "smartphone", ""),
        (tr('Traps',
            'Pièges'), "/traps", "triangle-alert", ""),
    ]),
    ("CHERCHER", [
        ("Configuration", "/config", "settings", ""),
        (tr('What Bretzel can do',
            'Ce que Bretzel sait faire'), "/capabilities", "sparkles", ""),
        ("Catalogue ui.*", "/components", "shapes", ""),
        ("Runtime client", "/runtime", "cpu", ""),
        (tr("The framework's tree",
            "L'arbre du framework"), "/tree", "folder-tree", ""),
        ("Cheat-sheet", "/cheatsheet", "list", ""),
    ]),
]


_NAV_EN = {
    tr('GET STARTED',
       'DÉMARRER'): "GET STARTED", tr('THE CYCLE',
                                  'LE CYCLE'): "THE CYCLE",
    "CONSTRUIRE": "BUILD", tr('THE SUBJECTS',
                              'LES SUJETS'): "TOPICS", "CHERCHER": "REFERENCE",
    "Introduction": "Introduction", tr('Get started in 5 minutes',
                                       'Démarrer en 5 minutes'): "Start in 5 minutes",
    "Comprendre Bretzel": "Understand Bretzel", tr('Describe the UI',
                                                   "Décrire l'UI"): "Describe the UI",
    tr('Judge the code',
       'Juger le code'): "Review code", tr('State · server',
                                       'État · serveur'): "State · server",
    tr('State · client',
       'État · client'): "State · client", "Actions · serveur": "Actions · server",
    "Actions · client": "Actions · client", tr('Reactivity · server',
                                               'Réactivité · serveur'): "Reactivity · server",
    tr('Reactivity · client',
       'Réactivité · client'): "Reactivity · client", "Structure d'app": "App structure",
    "Carte de l'app": "App map", tr('Theme',
                                    'Thème'): "Theming", "Listes et tableaux": "Lists and tables",
    "Formulaires": "Forms", tr('Drag and drop',
                               'Glisser-déposer'): "Drag and drop", "Graphiques": "Charts",
    tr('The cadence',
       'La cadence'): "Cadence", tr('Scrolling',
                                'Le défilement'): "Scrolling", tr('The languages',
                                                              'Les langues'): "Languages",
    "Authentification": "Authentication", tr('The browser',
                                             'Le navigateur'): "The browser", tr('Traps',
                                                                             'Pièges'): "Pitfalls",
    "Configuration": "Configuration", tr('What Bretzel can do',
                                         'Ce que Bretzel sait faire'): "What Bretzel can do",
    "Catalogue ui.*": "ui.* catalogue", "Runtime client": "Client runtime",
    tr("The framework's tree",
       "L'arbre du framework"): "Framework tree", "Cheat-sheet": "Cheat sheet",
}


def localized_nav_label(label: str) -> str:
    return label if Language().code.startswith("fr") else _NAV_EN.get(label, label)


@layout
def shell() -> None:
    # Search and social metadata follows the request language, while the
    # rendered chapter itself remains the authoritative page content.
    ui.meta_tag(name="robots", content="index,follow,max-image-preview:large")
    ui.meta_tag(property="og:type", content="website")
    ui.meta_tag(property="og:site_name", content="Bretzel")
    ui.meta_tag(
        property="og:description",
        content=tr(
            "Bretzel documentation for server-driven, reactive Python web apps.",
            "Documentation Bretzel pour créer des applications web Python réactives et pilotées par le serveur.",
        ),
    )
    ui.meta_tag(name="twitter:card", content="summary")
    with ui.viewport():
        mobile = Screen().is_mobile
        navigation = DocsNavigation()
        sidebar = ui.sidebar(
            collapsible="overlay" if mobile else "rail",
            open=not mobile,
            width="lg",
        )
        with sidebar:
            ui.sidebar_title(
                tr("Bretzel Docs", "Documentation Bretzel"),
                icon=ui.icon("book-open", color="primary", size="lg"),
            )
            ui.input(
                value=navigation.query,
                placeholder=(tr('Search a page…',
                                'Rechercher une page…') if Language().code.startswith("fr")
                             else "Search documentation…"),
                icon_left="search",
                clearable=True,
                size="sm",
                classes="my-2 group-data-[open=false]/sidebar:hidden",
            )
            for section, items in NAV:
                with ui.sidebar_section(label=localized_nav_label(section)):
                    for label, path, icon, _blurb in ui.filter_each(
                        items,
                        query=navigation.query,
                        text=lambda item: f"{section} {item[0]}",
                        key=lambda item: item[1],
                    ):
                        ui.sidebar_item(localized_nav_label(label), icon=icon, href=path)
            with ui.sidebar_footer(
                name="Bretzel",
                subtitle=tr("v0.1.0a1 · Early alpha", "v0.1.0a1 · Alpha précoce"),
            ):
                ui.sidebar_footer_item(
                    label="English" + (" ✓" if Language().code == "en" else ""),
                    icon_left="languages", on_click=partial(Language.set, "en"),
                )
                ui.sidebar_footer_item(
                    label=tr('French',
                             'Français') + (" ✓" if Language().code == "fr" else ""),
                    icon_left="languages", on_click=partial(Language.set, "fr"),
                )
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=(label if Language().code.startswith("fr") else {
                            tr('Light theme',
                               'Thème clair'): "Light theme", tr('Dark theme',
                                                             'Thème sombre'): "Dark theme",
                            tr('System theme',
                               'Thème système'): "System theme",
                        }[label]),
                        icon_left=icon,
                        on_click=ColorScheme.set(value),
                    )
                # Le lien croisé. ``sidebar_title`` ramène déjà à ``/``
                # (son ``href`` par défaut), donc une entrée « Accueil »
                # ne servirait à rien — la place va à l'aller-retour entre
                # les deux apps de démo, qui tournent côte à côte en dev.
                # Le port est en dur parce que la cible est un AUTRE
                # serveur : rien côté doc ne peut le connaître.
                ui.sidebar_footer_item(
                    label="GitHub", icon_left="github",
                    href="https://github.com/JeanHoccart/bretzel",
                )
        with ui.pane(
            gap="none",
            padding="lg",
            classes="min-w-0 max-md:px-4 max-md:pt-20 2xl:px-12",
        ):
            if mobile:
                with ui.hstack(
                    align="center", gap="sm",
                    classes=(
                        "fixed inset-x-0 top-0 z-30 h-16 px-4 "
                        "bg-background/95 backdrop-blur "
                        "border-b border-text/10"
                    ),
                ):
                    ui.sidebar_trigger(sidebar, icon="menu", size="sm")
                    ui.text(tr("Bretzel Docs", "Documentation Bretzel"), weight="bold")
            ui.outlet()
