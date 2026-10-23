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


# Les trois modes, dans l'ordre où on les lit. MÊMES entrées que
# ``examples/playground/app/layout.py`` — les deux coques se lisent l'une
# après l'autre, et une entrée qui diffère se lit comme une différence de
# FRAMEWORK alors que ce n'en est pas une.
#
# Trois entrées et non un bascule : ``system`` est un état à part entière
# — « suis mon OS » — qu'un contrôle à deux positions ne sait pas
# exprimer. On choisit, on ne devine pas dans quel sens ça va basculer.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", 'Light theme', "sun"),
    ("dark", 'Dark theme', "moon"),
    ("system", 'System theme', "monitor"),
)


class DocsNavigation(ClientState):
    """Recherche locale dans le sommaire, sans requête serveur."""

    query: str = field(default="")


# The picture a shared link shows (Slack, LinkedIn, X). Absolute, because
# a crawler reads it outside any page; served by the landing.
SHARE_IMAGE = "https://bretzel-py.dev/assets/bretzel-mark.png"

# The other public Bretzel sites, for the footer menu: (label, icon, url).
SITES: tuple[tuple[str, str, str], ...] = (
    ("Website", "globe", "https://bretzel-py.dev"),
    ("Component gallery", "shapes", "https://ui.bretzel-py.dev"),
    ("Live Kanban", "kanban", "https://demo.bretzel-py.dev"),
    ("GitHub", "github", "https://github.com/JeanHoccart/bretzel"),
)

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
    ('GET STARTED', [
        ("Introduction", "/", "compass", ""),
        ('Start in 5 minutes', "/quickstart", "rocket", ""),
        ('Understand Bretzel', "/how", "book-open", ""),
        ('How it compares', "/compare", "scale", ""),
        ('Describe the UI', "/describe", "layout-template", ""),
        # Le jumeau du précédent : l'un dit ce qui existe, l'autre juge
        # ce qu'on en a fait. Ils se lisent l'un après l'autre.
        ('Review code', "/check", "shield-check", ""),
    ]),
    ('THE CYCLE', [
        ('State · server', "/state-server", "database", ""),
        ('State · client', "/state-client", "monitor", ""),
        ('Actions · server', "/actions-server", "mouse-pointer-click", ""),
        ("Actions · client", "/actions-client", "terminal", ""),
        ('Reactivity · server', "/reactivity-server", "zap", ""),
        ('Reactivity · client', "/reactivity-client", "activity", ""),
    ]),
    ('BUILD', [
        ('App structure', "/structure", "layers", ""),
        ('App map', "/app-map", "network", ""),
        ('Theming', "/theme", "palette", ""),
    ]),
    ('TOPICS', [
        # ⚠️ Renommé le 2026-09-03. Il s'appelait « Capacités
        # navigateur », voisin immédiat de « Ce que Bretzel sait
        # faire » : deux entrées dont les noms se confondaient alors
        # qu'elles ne font pas le même métier — l'une enseigne,
        # l'autre indexe.
        #
        # Les sept suivants sont arrivés le 2026-09-03 : la section
        # n'avait que deux entrées alors que HUIT capacités n'avaient
        # aucun chapitre. Le cliquet de `test_a_capability_is_anchored`
        # tombe donc de 8 à 0. `/lists` en couvre deux — la liste et
        # le tableau sont le même besoin à deux échelles.
        ('Lists and tables', "/lists", "table", ""),
        ('Forms', "/forms", "clipboard-list", ""),
        ('Drag and drop', "/drag", "move", ""),
        ('Charts', "/charts", "chart-line", ""),
        ('Cadence', "/cadence", "timer", ""),
        ('Scrolling', "/scrolling", "scroll", ""),
        ('Languages', "/languages", "languages", ""),
        ('Authentication', "/auth", "key-round", ""),
        ('The browser', "/browser", "smartphone", ""),
        ('Pitfalls', "/traps", "triangle-alert", ""),
    ]),
    ('REFERENCE', [
        ("Configuration", "/config", "settings", ""),
        ('What Bretzel can do', "/capabilities", "sparkles", ""),
        ('ui.* catalogue', "/components", "shapes", ""),
        ('Component gallery', "https://ui.bretzel-py.dev", "layout-grid", ""),
        ('Client runtime', "/runtime", "cpu", ""),
        ('Framework tree', "/tree", "folder-tree", ""),
        ('Cheat sheet', "/cheatsheet", "list", ""),
    ]),
]


@layout
def shell() -> None:
    ui.meta_tag(name="robots", content="index,follow,max-image-preview:large")
    ui.meta_tag(property="og:type", content="website")
    ui.meta_tag(property="og:site_name", content="Bretzel")
    ui.meta_tag(
        property="og:description",
        content="Bretzel documentation for server-driven, reactive Python web apps.",
    )
    ui.meta_tag(property="og:image", content=SHARE_IMAGE)
    ui.meta_tag(name="twitter:card", content="summary")
    ui.meta_tag(name="twitter:image", content=SHARE_IMAGE)
    with ui.viewport():
        mobile = Screen().is_mobile
        navigation = DocsNavigation()
        sidebar = ui.sidebar(
            collapsible="overlay" if mobile else "rail",
            open=not mobile,
        )
        with sidebar:
            ui.sidebar_title(
                "Bretzel Docs",
                icon=ui.icon("book-open", color="primary", size="lg"),
            )
            ui.input(
                value=navigation.query,
                placeholder='Search documentation…',
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
                subtitle="v0.1.0a3 · Early alpha",
            ):
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=label,
                        icon_left=icon,
                        on_click=ColorScheme.set(value),
                    )
                ui.divider(classes="my-1")
                # The way to the other public Bretzel sites — the same
                # list, in the same order, in the gallery's footer. The
                # docs themselves are left out: ``sidebar_title`` already
                # leads home.
                for label, icon, href in SITES:
                    ui.sidebar_footer_item(label=label, icon_left=icon, href=href)
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
