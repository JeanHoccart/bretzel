"""kanban/tableau — les colonnes, les cartes, et le fil d'activité.

Deux zones, et **le partage des deux listes de ``@refreshable`` est tout
le sujet de cet exemple** :

- ``deps=`` répond à « qu'est-ce qui me fait me re-rendre, MOI » — la
  réponse arrive dans la réponse de mon action, un aller-retour.
- ``broadcast=`` répond à « qu'est-ce que les AUTRES fenêtres doivent
  refaire » — un signal SSE puis leur propre requête.

Le tableau est dans les deux : je le change, et les autres doivent le
voir. Les filtres ne sont que dans ``deps`` : ce que je masque ne regarde
que moi, et le diffuser referait travailler tout le monde à chaque frappe
d'une seule personne.

**La colonne qui défile EST la zone de dépôt**, pas un conteneur autour
d'elle. Poser la ``dropzone`` à l'intérieur du bloc qui défile ferait
glisser sa boîte avec les cartes : son cadre couperait le milieu de la
colonne, et le surlignage « ici, tu peux lâcher » sortirait de l'écran au
moment précis où il sert (mesuré sur ``examples/crm``).
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, page, refreshable, ui
from examples.kanban.features.donnees import (
    COLONNES,
    COUL_ETIQUETTE,
    COULEURS,
    INITIALES,
    LIB_ETIQUETTE,
    NOMS,
    Tableau,
    avancement,
    colonne_de,
    depuis,
    echeance_lisible,
    occupation,
)
from examples.kanban.features.fiche import tiroir
from examples.kanban.features.logic import (
    GROUPE,
    ZONE_ARCHIVE,
    archiver,
    deposer,
    ouvrir,
)
from examples.kanban.features.shell import shell
from examples.kanban.features.state import Affichage, Filtres


def vignette(carte: dict) -> None:
    """Une carte, telle qu'elle se lit sans l'ouvrir.

    Le clic ouvre le tiroir et le glisser la déplace, sans se marcher
    dessus : le socle n'arme un glissement qu'après un déplacement du
    pointeur (ou un appui maintenu au doigt), donc un clic franc reste un
    clic.
    """
    faites, total = avancement(carte)
    with ui.card(padding="sm", hoverable=True,
                 on_click=partial(ouvrir, carte["id"])), ui.vstack(gap="xs"):
        if carte["etiquettes"]:
            with ui.hstack(gap="xs", wrap=True):
                for cle in carte["etiquettes"]:
                    ui.badge(LIB_ETIQUETTE[cle], size="xs",
                             variant="soft", color=COUL_ETIQUETTE[cle])
        ui.text(carte["titre"], size="sm", weight="medium")
        with ui.hstack(justify="between", align="center", gap="sm"):
            with ui.hstack(gap="sm", align="center"):
                if total:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("square-check-big", size="xs",
                                color="success" if faites == total
                                else "muted")
                        ui.text(f"{faites}/{total}", size="xs",
                                color="muted")
                if carte["echeance"]:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("calendar", size="xs", color="muted")
                        ui.text(echeance_lisible(carte["echeance"]),
                                size="xs", color="muted")
                if carte["commentaires"]:
                    with ui.hstack(gap="xs", align="center"):
                        ui.icon("message-circle", size="xs",
                                color="muted")
                        ui.text(str(len(carte["commentaires"])),
                                size="xs", color="muted")
            with ui.hstack(gap="xs", align="center"):
                if carte["points"]:
                    ui.badge(str(carte["points"]), size="xs",
                             variant="soft", color="muted")
                ui.avatar(initials=INITIALES[carte["qui"]], size="xs",
                          color=COULEURS[carte["qui"]],
                          tooltip=NOMS[carte["qui"]])


def colonne(cle: str, libelle: str, limite: int | None) -> None:
    """Une colonne : son en-tête, sa limite, et sa zone de dépôt."""
    filtres = Filtres()
    cartes = colonne_de(cle, filtres.qui, filtres.etiquette, filtres.q)
    dedans = occupation(cle)
    saturee = limite is not None and dedans >= limite

    with ui.vstack(gap="sm", classes="flex-1 min-w-56 min-h-0"):
        with ui.hstack(justify="between", align="center",
                       classes="px-1 shrink-0"):
            with ui.hstack(gap="xs", align="center"):
                ui.heading(libelle, level=2, size="sm")
                # ⚠️ Le ``tooltip=`` est posé sur TOUTES les colonnes, y
                # compris celles sans limite. Il enveloppe le badge, donc
                # n'en coiffer que deux décalait leurs en-têtes de deux
                # pixels par rapport aux autres — visible à la capture.
                ui.badge(
                    f"{dedans} / {limite}" if limite else str(dedans),
                    size="xs", variant="soft",
                    color="error" if saturee else "muted",
                    tooltip=(f"Limite d'en-cours : {limite} cartes"
                             if limite else "Pas de limite d'en-cours"),
                )
            if len(cartes) != dedans:
                ui.text(f"{len(cartes)} affichée"
                        + ("s" if len(cartes) > 1 else ""),
                        size="xs", color="muted")

        # ⚠️ C'est la ZONE qui défile. ``min-h-0`` est ce qui autorise un
        # enfant de flex à être PLUS PETIT que son contenu — sans lui,
        # ``overflow-y-auto`` n'a rien à couper et la colonne pousse la
        # page.
        with ui.dropzone(
            name=cle, accepts=[GROUPE], on_move=deposer, color="primary",
            classes="flex-1 min-h-0 overflow-y-auto rounded-lg p-2 "
                    + ("bg-error/5" if saturee else "bg-text/5"),
        ), ui.vstack(gap="sm"):
            for carte in ui.drag_each(cartes, group=GROUPE, key="id"):
                vignette(carte)
            if not cartes:
                ui.text("Rien ici. Lâche une carte.", size="xs",
                        color="muted", classes="px-1 py-6 text-center")


def bande_archive() -> None:
    """La sortie du tableau : une bande, sous les colonnes.

    ⚠️ **Sa hauteur est FIXE et son débordement coupé**, et ce n'est pas
    de la coquetterie. Le moteur de glisser reparente le nœud déplacé
    dans la zone survolée — c'est ce qui fait que l'ordre du DOM EST le
    résultat au lâcher. Une zone qui se laisse dimensionner par ce
    qu'elle héberge grandit donc de la taille d'une carte au survol, et
    pousse tout ce qui l'entoure au moment précis où on vise. Mesuré :
    la première version, posée dans le bandeau, passait de 104×32 à
    362×105 et faisait sauter la barre entière de 93 à 166 px.

    Ici la carte accueillie est simplement coupée : ce que le lecteur
    regarde pendant le geste, c'est l'aperçu sous son pointeur.
    """
    with ui.dropzone(
        name=ZONE_ARCHIVE, accepts=[GROUPE], locked=True, on_move=archiver,
        color="error",
        classes="flex-none h-14 min-h-0! overflow-hidden rounded-lg "
                "border border-dashed border-text/20 flex items-center "
                "justify-center gap-2",
    ):
        ui.icon("archive", size="sm", color="muted")
        ui.text("Lâche une carte ici pour l'archiver", size="xs",
                color="muted")


@refreshable(deps=[Tableau, Filtres], broadcast=[Tableau])
def plateau() -> None:
    """Les quatre colonnes. Diffusé : ce que je glisse, les autres le voient."""
    with ui.vstack(gap="sm", classes="flex-1 min-h-0 min-w-0 p-4"):
        with ui.hstack(gap="md", align="stretch",
                       classes="flex-1 min-h-0 min-w-0 overflow-x-auto"):
            for cle, libelle, limite in COLONNES:
                colonne(cle, libelle, limite)
        bande_archive()


@refreshable(deps=[Tableau], broadcast=[Tableau])
def activite() -> None:
    """Le fil d'activité — l'histoire du tableau, la plus récente en haut.

    C'est ce panneau qui rend le partage VISIBLE : dans la seconde
    fenêtre, une ligne apparaît sans que personne n'y ait touché. Les
    entrées déjà annulées restent affichées, en retrait — la pile est
    devant le curseur, elle n'est pas effacée tant qu'on n'a rien réécrit.

    ⚠️ **Le déploiement du panneau ne passe PLUS par le serveur.** Il
    vivait dans ``Vue`` (état serveur), donc replier une colonne coûtait
    un aller-retour, le re-rendu de cette zone, et l'attente — pour
    basculer une classe. Les deux versions sont maintenant rendues et
    ``visible=`` en cache une : zéro requête, et ``Vue`` sort des
    dépendances de la zone.
    """
    affichage = Affichage()
    tableau = Tableau()

    # Le rail, quand le panneau est replié. Rendu en permanence — c'est
    # ce qui permet de basculer sans rien demander à personne.
    with ui.vstack(align="center", visible=~affichage.activite,
                   classes="flex-none w-12 border-l border-text/10 pt-4"):
        ui.icon_button("panel-right-open", variant="ghost", size="sm",
                       on_click=affichage.activite.set(True),
                       tooltip="Montrer l'activité")

    with ui.pane(padding="none", gap="none", visible=affichage.activite,
                 classes="flex-none w-80 border-l border-text/10"):
        with ui.hstack(justify="between", align="center",
                       classes="px-4 py-3 shrink-0"):
            ui.heading("Activité", level=2, size="sm")
            ui.icon_button("panel-right-close", variant="ghost", size="sm",
                           on_click=affichage.activite.set(False),
                           tooltip="Cacher l'activité")
        with ui.pane(padding="md", gap="sm", classes="flex-1 min-h-0"):
            if not tableau.journal:
                ui.text("Personne n'a encore rien fait. Glisse une carte.",
                        size="xs", color="muted")
            for rang, entree in reversed(list(enumerate(tableau.journal))):
                defaite = rang >= tableau.curseur
                with ui.hstack(gap="sm", align="start",
                               classes="opacity-40" if defaite else ""):
                    ui.avatar(initials=INITIALES[entree["qui"]], size="xs",
                              color=COULEURS[entree["qui"]])
                    with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                        ui.text(f"{NOMS[entree['qui']]} {entree['texte']}",
                                size="xs")
                        with ui.hstack(gap="xs", align="center"):
                            ui.text(depuis(entree["t"]), size="xs",
                                    color="muted")
                            if defaite:
                                ui.badge("annulé", size="xs", variant="soft",
                                         color="muted")


@page("/", layout=shell, title="Tableau")
def page_tableau() -> None:
    # ⚠️ ``align="stretch"`` n'est pas décoratif : ``ui.hstack`` aligne en
    # ``center`` par défaut — le choix juste pour une ligne de contrôles,
    # et fatal pour une ligne de COLONNES. Sans lui, chaque enfant prend
    # la hauteur de son contenu au lieu de celle du rang : la zone du
    # tableau mesurait 878 px dans un ``<main>`` de 591, débordait par le
    # bas, et comme le document est gelé (``ui.viewport``) rien ne
    # défilait — ni la page, ni la colonne, dont l'``overflow-y-auto``
    # n'avait plus rien à couper. Invisible sur un grand écran : à
    # 1500×940 tout tenait, à 1280×700 les cartes disparaissaient sous le
    # bord. Mesuré le 2026-09-09 sur une capture de l'utilisateur.
    with ui.hstack(gap="none", align="stretch",
                   classes="flex-1 min-h-0 w-full"):
        plateau()
        activite()
    tiroir()


#: ⚠️ ``tiroir`` est déclaré ici alors qu'il vit dans ``fiche.py``, et
#: c'est voulu : une ``Feature`` est le contrat d'une TRANCHE, pas d'un
#: fichier. Le tiroir de détail est une région de cette page, il n'a ni
#: route ni ``layout=`` — le vocabulaire des dix ``kind`` n'a d'ailleurs
#: rien pour un fragment rendu qui ne soit ni l'un ni l'autre. Le socle
#: capte le module de DÉFINITION de chaque symbole, donc la carte pointe
#: quand même le bon fichier.
feature = Feature(
    name="tableau", kind="page",
    provides=[page_tableau, plateau, activite, tiroir, colonne,
              vignette, bande_archive],
    uses=["donnees", "state", "logic", "shell"],
)
