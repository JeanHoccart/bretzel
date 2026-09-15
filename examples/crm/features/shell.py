"""features/shell — shell : le cadre racine, et l'écran 12 (coque responsive).

``ui.viewport`` + ``ui.pane`` portent le cadre et sa région qui défile —
plus aucune chaîne de classes à recopier ici, et plus de ``min-h-0``
load-bearing à ne pas oublier. Le POURQUOI vit dans les thèmes des deux
composants ; cf. aussi ``app-structure.md`` § 5.

**Le responsive est un `if` SERVEUR**, pas du CSS : ``Screen().is_mobile``
est un vrai `bool` lu du cookie `bz_screen` au rendu, donc **un seul arbre
existe dans le DOM**. C'est l'échappatoire prévue pour un swap STRUCTUREL —
un rail à gauche et une tab bar en bas ne sont pas la même nav habillée
autrement, et aucune requête média ne les échange proprement
(``screen-responsive-nav.md``).

Ce que le CRM y met sous contrainte et qu'aucune app n'avait : **onze
routes**. Un rail les porte toutes ; une tab bar en porte cinq — donc le
mobile doit CHOISIR, et le choix est du code, pas une feuille de style.

⚠️ Pas de live-resize, par décision de conception : la correction est au
chargement. Traverser 768 px en redimensionnant demande un rechargement.
"""

from __future__ import annotations

from bretzel import Feature, Screen, layout, refreshable, ui
from bretzel.theme import ColorScheme

from examples.crm.core.domain import ROLES
from examples.crm.features.access import (
    ViewerPrefs,
    current_profile,
    is_director,
    portfolio_options,
    set_portfolio,
    sign_out,
)

#: La nav complète — libellé, icône, route. Le rail la rend en entier.
NAV: tuple[tuple[str, str, str], ...] = (
    ("Pipeline", "columns-3", "/"),
    ("Comptes", "building-2", "/comptes"),
    ("Contacts", "users", "/contacts"),
    ("Activités", "calendar-days", "/activites"),
)
PILOTAGE: tuple[tuple[str, str, str], ...] = (
    ("Rapports", "chart-column", "/rapports"),
    ("Recherche", "search", "/recherche"),
    ("Temps réel", "radio", "/temps-reel"),
)
OUTILS: tuple[tuple[str, str, str], ...] = (
    ("Import", "upload", "/import"),
    ("Paramètres", "settings", "/parametres"),
    ("Carte de l'app", "network", "/_map"),
)

#: Les cinq onglets du mobile. Ce sont les cinq gestes quotidiens, pas les
#: cinq premiers du rail : une tab bar à largeur égale devient illisible
#: au-delà, et « Carte de l'app » n'est pas un geste quotidien.
TABS: tuple[tuple[str, str, str], ...] = (
    ("Pipeline", "columns-3", "/"),
    ("Comptes", "building-2", "/comptes"),
    ("Contacts", "users", "/contacts"),
    ("Activités", "calendar-days", "/activites"),
    ("Chercher", "search", "/recherche"),
)


#: Les trois modes de couleur et leur icône, pour le menu du pied de
#: barre. Le libellé long vit dans ``settings.py`` — ici c'est un
#: raccourci, pas le réglage.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", "Thème clair", "sun"),
    ("dark", "Thème sombre", "moon"),
    ("system", "Thème système", "monitor"),
)


@refreshable(deps=[ViewerPrefs])
def portfolio_picker() -> None:
    """Le sélecteur de portefeuille — DIRECTION seulement.

    Rendu dans la barre latérale : ailleurs, le choix n'aurait pas de
    place — il porte sur les DOUZE écrans, donc il appartient au cadre,
    pas à une page.

    **Il disparaît quand la sidebar se replie**, section comprise. Le
    pari « un ``ui.select`` dans un ``ui.sidebar`` en ``rail`` » a été
    mesuré le 2026-08-29 et il est perdu des deux côtés : le PANNEAU
    tombait à 31 px (réparé dans le socle, ``MIN_MATCHED_WIDTH``), et la
    GÂCHETTE reste un carré de 31 px à chevron nu, qui ne dit ni ce
    qu'il fait ni ce qui est choisi. Les autres enfants de la sidebar
    ont une forme rail (l'entrée devient une icône, le libellé de
    section devient un trait) ; un select n'en a pas.

    La classe est posée sur la SECTION, pas sur le champ : cachée sur le
    seul champ, la section rendrait encore son ``section_divider`` — le
    trait qui remplace le titre dans le rail — donc un séparateur sans
    rien dessous.
    """
    if not is_director():
        return
    with ui.sidebar_section(
        label="PORTEFEUILLE",
        classes="group-data-[open=false]/sidebar:hidden",
    ):
        with ui.vstack(gap="none", classes="px-2 pb-2"):
            ui.select(value=ViewerPrefs().portefeuille,
                      options=portfolio_options(), size="sm",
                      on_change=set_portfolio)


@refreshable(deps=[ViewerPrefs])
def viewer_footer() -> None:
    """Qui est connecté, et la seule sortie.

    Le sous-titre porte le RÔLE. Il a d'abord porté le cadrage effectif,
    ce qui donnait « Sofia Rossi / Sofia Rossi » à l'écran pour un
    commercial — chez qui les deux sont le même mot. Le portefeuille d'un
    directeur, lui, est déjà écrit dans son sélecteur juste au-dessus.

    ⚠️ **Pas d'``avatar=``** : le composant dérive les initiales de
    ``name`` tout seul (``_footer_initials``), et les quatre autres
    exemples qui l'instancient le laissent faire. Les calculer ici
    donnait le même résultat sur les sept comptes — donc c'était du
    travail en double, pas un réglage.
    """
    profile = current_profile()
    if profile is None:
        return
    with ui.sidebar_footer(
        name=profile["display_name"],
        subtitle=ROLES[profile["role"]],
    ):
        # Le thème est atteignable de PARTOUT, pas seulement depuis
        # les paramètres : c'est un réglage de confort de lecture, et
        # traverser une page pour baisser la luminosité n'a pas de sens.
        # ``ColorScheme.set`` rend de la source client — le clic ne part
        # pas au serveur.
        for value, label, icon in THEME_ITEMS:
            ui.sidebar_footer_item(label=label, icon_left=icon,
                                   on_click=ColorScheme.set(value))
        ui.sidebar_footer_item(label="Paramètres", icon_left="settings",
                               href="/parametres")
        ui.sidebar_footer_item(label="Se déconnecter", icon_left="log-out",
                               color="error", on_click=sign_out)


@layout
def shell() -> None:
    mobile = Screen().is_mobile
    with ui.viewport():
        # UN seul ``ui.sidebar``, MÊMES enfants, deux modes de repli.
        # - desktop → ``rail`` : replié, il reste une bande d'icônes, et
        #   onze routes valent une bande permanente.
        # - mobile  → ``overlay`` : il sort du flux et glisse au-dessus,
        #   fond assombri, Escape. ``rail`` sur un téléphone mangerait un
        #   cinquième de la largeur en permanence.
        sidebar = ui.sidebar(collapsible="overlay" if mobile else "rail",
                             open=not mobile)
        with sidebar:
            ui.sidebar_title(
                "Bretzel CRM",
                icon=ui.icon("handshake", color="primary", size="lg"),
            )
            for section, items in (("VENTES", NAV), ("PILOTAGE", PILOTAGE),
                                   ("OUTILS", OUTILS)):
                with ui.sidebar_section(label=section):
                    for label, icon, href in items:
                        ui.sidebar_item(label, icon=icon, href=href)
            portfolio_picker()
            viewer_footer()
        with ui.pane(gap="none"):
            if mobile:
                # ⚠️ Le hamburger appartient à l'APP, pas au composant : en
                # mode ``overlay`` la barre est ``fixed`` HORS de l'écran
                # (mesuré : x = -256), et son propre bouton de repli part
                # avec elle (x = -148). Sans ce déclencheur, six des onze
                # routes deviennent injoignables sur mobile — la tab bar
                # n'en porte que cinq. Le framework REFUSE désormais de
                # rendre cette composition sans un moyen de revenir.
                with ui.hstack(
                    justify="between", align="center",
                    classes="sticky top-0 z-20 bg-background "
                            "px-4 py-2 border-b border-text/10",
                ):
                    # ``ui.sidebar_trigger`` : il câble la barre, émet
                    # l'``aria-controls``, et c'est lui que la garde
                    # d'atteignabilité attend. Plus d'``attrs=`` pour le
                    # nom accessible depuis le 2026-08-24 : il vient de
                    # ``texts["sidebar.toggle"]``, déclaré une fois dans
                    # ``main.py`` avec les 46 autres.
                    ui.sidebar_trigger(sidebar, icon="menu")
                    ui.text("Bretzel CRM", weight="semibold")
                    ui.icon("handshake", color="primary")
            with ui.vstack(gap="none", classes="p-8 max-md:px-4 max-md:py-4"):
                ui.outlet()
            if mobile:
                # La tab bar est le DERNIER enfant de la colonne qui défile,
                # pas un frère du shell. Son thème est ``sticky bottom-0`` et
                # non ``fixed`` : elle reste dans le flux, donc elle réserve
                # sa propre hauteur et rien n'a besoin d'un fond de page.
                # Posée dehors, elle n'a plus de conteneur de défilement à
                # quoi se coller — mesuré : elle se rendait EN HAUT, à y=0,
                # parce que le shell ``fixed inset-0`` l'avait quittée.
                with ui.bottom_bar():
                    for label, icon, href in TABS:
                        ui.bottom_bar_item(label=label, icon=icon, href=href)


feature = Feature(name="shell", kind="shell", provides=[shell],
                  uses=["access"])
