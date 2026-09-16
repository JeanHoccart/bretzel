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

from bretzel import Screen, layout, ui
from bretzel.state import ClientState, field
from bretzel.theme import ColorScheme

#: Les trois modes, dans l'ordre où on les lit. MÊME tuple que
#: ``examples/playground/app/layout.py`` — les deux coques se lisent l'une
#: après l'autre, et une entrée qui diffère se lit comme une différence de
#: FRAMEWORK alors que ce n'en est pas une.
#:
#: Trois entrées et non un bascule : ``system`` est un état à part entière
#: — « suis mon OS » — qu'un contrôle à deux positions ne sait pas
#: exprimer. On choisit, on ne devine pas dans quel sens ça va basculer.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", "Thème clair", "sun"),
    ("dark", "Thème sombre", "moon"),
    ("system", "Thème système", "monitor"),
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
    ("DÉMARRER", [
        ("Introduction", "/", "compass", ""),
        ("Démarrer en 5 minutes", "/quickstart", "rocket", ""),
        ("Comprendre Bretzel", "/how", "book-open", ""),
        ("Décrire l'UI", "/describe", "layout-template", ""),
        # Le jumeau du précédent : l'un dit ce qui existe, l'autre juge ce
        # qu'on en a fait. Ils se lisent l'un après l'autre.
        ("Juger le code", "/check", "shield-check", ""),
    ]),
    ("LE CYCLE", [
        ("État · serveur", "/state-server", "database", ""),
        ("État · client", "/state-client", "monitor", ""),
        ("Actions · serveur", "/actions-server", "mouse-pointer-click", ""),
        ("Actions · client", "/actions-client", "terminal", ""),
        ("Réactivité · serveur", "/reactivity-server", "zap", ""),
        ("Réactivité · client", "/reactivity-client", "activity", ""),
    ]),
    ("CONSTRUIRE", [
        ("Structure d'app", "/structure", "layers", ""),
        ("Carte de l'app", "/app-map", "network", ""),
        ("Thème", "/theme", "palette", ""),
    ]),
    ("LES SUJETS", [
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
        ("Glisser-déposer", "/drag", "move", ""),
        ("Graphiques", "/charts", "chart-line", ""),
        ("La cadence", "/cadence", "timer", ""),
        ("Le défilement", "/scrolling", "scroll", ""),
        ("Les langues", "/languages", "languages", ""),
        ("Authentification", "/auth", "key-round", ""),
        ("Le navigateur", "/browser", "smartphone", ""),
        ("Pièges", "/traps", "triangle-alert", ""),
    ]),
    ("CHERCHER", [
        ("Configuration", "/config", "settings", ""),
        ("Ce que Bretzel sait faire", "/capabilities", "sparkles", ""),
        ("Catalogue ui.*", "/components", "shapes", ""),
        ("Runtime client", "/runtime", "cpu", ""),
        ("L'arbre du framework", "/tree", "folder-tree", ""),
        ("Cheat-sheet", "/cheatsheet", "list", ""),
    ]),
]


@layout
def shell() -> None:
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
                "Bretzel Docs",
                icon=ui.icon("book-open", color="primary", size="lg"),
            )
            ui.input(
                value=navigation.query,
                placeholder="Rechercher une page…",
                icon_left="search",
                clearable=True,
                size="sm",
                classes="my-2 group-data-[open=false]/sidebar:hidden",
            )
            for section, items in NAV:
                with ui.sidebar_section(label=section):
                    for label, path, icon, _blurb in ui.filter_each(
                        items,
                        query=navigation.query,
                        text=lambda item: f"{section} {item[0]}",
                        key=lambda item: item[1],
                    ):
                        ui.sidebar_item(label, icon=icon, href=path)
            with ui.sidebar_footer(
                name="Bretzel",
                subtitle="v0.1.0a1 · Early alpha",
            ):
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=label,
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
                    ui.text("Bretzel Docs", weight="bold")
            ui.outlet()
