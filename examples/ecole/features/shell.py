"""features/shell — shell : le cadre racine, la barre latérale permanente.

*« Une barre latérale permanente à gauche : les classes, la recherche,
les réglages, le cahier de texte. L'ancienne version empilait tout dans
une barre d'outils horizontale qui débordait »* (§ 8 du cahier).

Elle ne porte pour l'instant qu'une entrée : le lot 1 ne livre qu'un
écran. Les suivantes arrivent avec leurs lots — une nav qui annonce des
routes inexistantes est pire qu'une nav courte.

**Le modèle de défilement : le document GELÉ** — ``ui.viewport`` +
``ui.pane``. C'est celui des outils, et cette app en est un : *« la
tablette est un poste de travail, pas une consultation »* (EF-U3). Il se
paie d'une chaîne de hauteurs continue de la racine à la région, et il
achète des régions à défilement indépendant — ce dont la grille du lot 3
aura besoin, avec son en-tête de dates qui ne doit pas partir vers le
haut quand on descend dans les créneaux du soir.

⚠️ **Les deux zones de ce fichier sont ``@refreshable``, et ce n'est pas
décoratif.** Un ``@layout`` est rendu UNE fois par chargement de page :
tout ce qui y lit un état mutable sans être une zone est gelé pour
toujours. Le sélecteur d'année afficherait donc la nouvelle année pendant
que le bandeau continuerait de dire l'ancienne — l'écran montrerait la
contradiction sans la signaler. C'est le silence B2 de
``livrer-une-app.md``, payé deux fois ailleurs.
"""

from __future__ import annotations

from bretzel import Feature, Screen, fullscreen, layout, refreshable, ui
from bretzel.theme import ColorScheme
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    bandeau_consultation,
    selecteur_annee,
)

#: La nav. Elle grandit d'un lot à l'autre : accueil et réglages
#: (lots 1-2), puis l'emploi du temps, le cahier de texte, la
#: recherche. Une entrée n'y apparaît que quand sa route existe —
#: c'est le piège n° 14 du cahier, « écrire un écran avant ses
#: routes », vu depuis la nav.
NAV: tuple[tuple[str, str, str], ...] = (
    ("Emploi du temps", "calendar-days", "/"),
    ("Mes classes", "layout-grid", "/classes"),
    ("Cahier de texte", "notebook-pen", "/cahier"),
    ("Chercher un élève", "search", "/recherche"),
)

#: Ce qui se règle une fois par an, à part du quotidien.
OUTILS: tuple[tuple[str, str, str], ...] = (
    ("Import et archives", "upload", "/import"),
    ("Réglages", "settings", "/reglages"),
)

#: Les trois modes de couleur et leur icône.
THEMES: tuple[tuple[str, str, str], ...] = (
    ("light", "Thème clair", "sun"),
    ("dark", "Thème sombre", "moon"),
    ("system", "Thème système", "monitor"),
)


@refreshable(deps=[AnneeVue], name="annee_picker")
def zone_annee() -> None:
    selecteur_annee()


@refreshable(deps=[AnneeVue], name="bandeau_annee")
def zone_bandeau() -> None:
    bandeau_consultation()


@layout
def shell() -> None:
    # ``is_touch`` et pas ``is_mobile`` : EF-U4 dit que le plein écran ne
    # s'affiche QUE là où il fonctionne, et le contre-exemple nommé est
    # Safari sur tablette — une question de moteur, pas de largeur. Un
    # iPad en paysage est large et ne sait pas le faire.
    #
    # ⚠️ **C'est une approximation, et elle est notée comme finding.** Le
    # vrai test est ``document.fullscreenEnabled``, qui vit dans le
    # navigateur ; Bretzel n'expose aucune capacité cliente à lire depuis
    # Python. Le pointeur grossier est le plus proche substitut dont
    # dispose le serveur, et il se trompe sur une tablette Android — où
    # le plein écran marche et où le bouton sera caché.
    plein_ecran_utile = not Screen().is_touch

    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            ui.sidebar_title(
                "École",
                icon=ui.icon("flask-conical", color="primary", size="lg"),
            )
            for section, entrees in (("SUIVI", NAV), ("OUTILS", OUTILS)):
                with ui.sidebar_section(label=section):
                    for label, icon, href in entrees:
                        ui.sidebar_item(label, icon=icon, href=href)
            with ui.sidebar_footer(name="Physique-chimie",
                                   subtitle=annee_regardee()["libelle"]):
                # EF-U2 : l'année se change depuis la barre latérale, et
                # le PIED est le seul endroit qui survive au repli en
                # rail (cf. la docstring de `selecteur_annee`). Son
                # sous-titre porte l'année regardée, donc l'information
                # reste lisible même quand le menu est fermé.
                zone_annee()
                ui.divider()
                for valeur, label, icon in THEMES:
                    ui.sidebar_footer_item(label=label, icon_left=icon,
                                           on_click=ColorScheme.set(valeur))
                if plein_ecran_utile:
                    ui.sidebar_footer_item(
                        label="Plein écran", icon_left="expand",
                        on_click=fullscreen(),
                    )
        # ``padding="md"`` et pas ``lg`` : l'écran le plus contraint
        # de l'app est une grille de SIX jours qui doit tenir en
        # largeur, et le cadre est ce qu'on peut lui rendre.
        with ui.pane(gap="md", padding="md"):
            zone_bandeau()
            ui.outlet()


feature = Feature(name="shell", kind="shell", provides=[shell],
                  uses=["annees"])
