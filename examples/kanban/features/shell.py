"""kanban/shell — le bandeau, et le cadre gelé qui porte le tableau.

``ui.viewport`` : le document ne défile jamais, ce sont les colonnes qui
défilent, chacune la sienne. C'est obligatoire pour un tableau — une
colonne pleine qui pousserait la page vers le bas emporterait les trois
autres et le bandeau avec elles.

**Les contrôles de filtre vivent ICI, hors de toute zone
``@refreshable``.** Une zone qui contiendrait le champ de recherche le
re-rendrait à chaque frappe temporisée, et le curseur repartirait au
début du mot. Le bandeau est donc rendu une fois ; seules les commandes
qui dépendent du tableau (annuler, rétablir, l'archive) sont une zone.

**Aucune ``ui.sidebar``, comme la messagerie et pour la même raison** :
l'app n'a qu'un écran. La navigation d'un kanban, ce sont ses colonnes.
"""

from __future__ import annotations

from bretzel import Feature, LiveConnection, layout, refreshable, ui
from bretzel.theme import ColorScheme
from examples.kanban.features.donnees import (
    COLONNES,
    COULEURS,
    ETIQUETTES,
    INITIALES,
    MEMBRES,
    Tableau,
)
from examples.kanban.features.logic import (
    annuler,
    archiver_ouverte,
    changer_de_membre,
    creer,
    filtrer,
    refaire,
)
from examples.kanban.features.state import Filtres, Moi, Nouvelle, Vue


@refreshable(deps=[Moi])
def identite() -> None:
    """« Tu es… » — l'identité de session, changeable en un clic.

    Deux fenêtres du même navigateur partagent le cookie, donc la même
    identité. Pour être quelqu'un d'autre, il faut une fenêtre privée —
    ou ce sélecteur, qui suffit à voir un journal signé de deux mains.

    ⚠️ **C'est une ZONE, et il a fallu un bug pour l'écrire.** La coque
    est rendue UNE fois : tout ce qui y lit un état mutable sans être une
    zone est gelé pour la vie de la page. Le sélecteur, lui, se mettait à
    jour tout seul — c'est un contrôle lié, sa valeur vit dans le
    navigateur — donc l'écran affichait le nouveau nom à côté de
    l'ANCIEN avatar, et rien ne signalait la contradiction. La coque de
    ``examples/messagerie`` porte le même avertissement, écrit trois
    jours plus tôt et pour la même raison.

    ``deps=[Moi]`` seul, sans ``broadcast`` : qui je suis ne regarde que
    moi.
    """
    moi = Moi()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.avatar(initials=INITIALES[moi.membre], size="xs",
                  color=COULEURS[moi.membre])
        ui.select(
            value=moi.membre,
            options=[(cle, nom) for cle, nom, _, _ in MEMBRES],
            on_change=changer_de_membre,
            size="sm",
            classes="w-44",
            tooltip="Qui tu es sur ce tableau",
        )


def connexion() -> None:
    """L'état du flux temps réel, lié — donc sans zone à rafraîchir.

    En faire une zone ``@refreshable`` ajouterait du HTML à chacune des
    réponses qu'elle prétend décrire.
    """
    live = LiveConnection()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.icon("radio", color="success", size="sm", visible=live.connected,
                tooltip="Tableau partagé — les autres fenêtres suivent")
        ui.icon("radio", color="muted", size="sm", visible=~live.connected,
                tooltip="Flux interrompu")


def dialogue_nouvelle() -> None:
    """Le dialogue de création. Ouvert par le bouton du bandeau."""
    nouvelle = Nouvelle()
    boite = ui.dialog(title="Nouvelle carte", width="sm")
    with boite, ui.form(on_submit=[creer, boite.close()]), ui.vstack(gap="md"):
        with ui.form_field(label="Titre", required=True):
            ui.input(value=nouvelle.titre, maxlength=120,
                     placeholder="Ce qu'il y a à faire")
        with ui.form_field(label="Colonne"):
            ui.select(value=nouvelle.colonne,
                      options=[(cle, lib) for cle, lib, _ in COLONNES])
        with ui.hstack(justify="end", gap="sm"):
            ui.button("Annuler", variant="ghost",
                      on_click=boite.close())
            ui.button("Créer", type="submit", color="primary",
                      icon_left="plus")
    ui.button("Nouvelle carte", color="primary", size="sm", icon_left="plus",
              on_click=boite.open())


@refreshable(deps=[Tableau, Vue], broadcast=[Tableau])
def commandes() -> None:
    """Annuler, rétablir, et la zone d'archive. Diffusées aux autres.

    Elles sont une zone parce qu'elles décrivent le tableau : le nombre
    d'annulations possibles change quand n'importe qui écrit, ici ou
    ailleurs. ``broadcast=[Tableau]`` fait suivre les autres fenêtres —
    sans quoi un bouton « Annuler » resterait grisé chez le voisin alors
    qu'il y a quelque chose à défaire.
    """
    tableau = Tableau()
    with ui.hstack(align="center", gap="xs", classes="shrink-0"):
        ui.icon_button(
            "undo-2", variant="ghost", size="sm", on_click=annuler,
            disabled=tableau.curseur == 0,
            tooltip=("Annuler : " + tableau.journal[tableau.curseur - 1]["texte"]
                     if tableau.curseur else "Rien à annuler"),
        )
        ui.icon_button(
            "redo-2", variant="ghost", size="sm", on_click=refaire,
            disabled=tableau.curseur >= len(tableau.journal),
            tooltip=("Rétablir : " + tableau.journal[tableau.curseur]["texte"]
                     if tableau.curseur < len(tableau.journal)
                     else "Rien à rétablir"),
        )
        # ⚠️ Un BOUTON ici, et la zone de dépôt est ailleurs — sous les
        # colonnes. La première version mettait la ``ui.dropzone`` dans ce
        # rang, et le moteur de glisser REPARENTE le nœud déplacé dans la
        # zone survolée : la cible passait de 104×32 à 362×105, et le
        # bandeau entier de 93 à 166 px de haut. Toute la barre sautait
        # sous le pointeur, au moment précis où on vise.
        #
        # C'est le modèle optimiste du socle, pas un défaut : au lâcher,
        # l'ordre du DOM EST le résultat. Mais une zone qui ne montrera
        # jamais ce qu'elle reçoit n'a rien à faire dans un rang de
        # contrôles — c'est la règle A2 de ``livrer-une-app.md``, écrite
        # le même jour et que j'avais enfreinte.
        ui.button(
            "Archiver", variant="outline", size="sm", icon_left="archive",
            on_click=archiver_ouverte, disabled=not Vue().ouverte,
            tooltip="Archiver la carte ouverte — ou lâche-en une sur la "
                    "bande, en bas du tableau",
        )


@layout
def shell() -> None:
    filtres = Filtres()
    with ui.viewport(direction="col"):
        with ui.vstack(gap="none",
                       classes="border-b border-text/10 shrink-0"):
            with ui.hstack(justify="between", align="center", gap="md",
                           classes="px-4 pt-2.5 pb-2"):
                with ui.hstack(align="center", gap="sm"):
                    ui.icon("kanban", color="primary", size="lg")
                    ui.heading("Refonte du portail client", level=1,
                               size="md")
                    ui.badge("Sprint 24", variant="soft", color="muted",
                             size="xs")
                with ui.hstack(align="center", gap="sm"):
                    connexion()
                    identite()
                    ui.icon_button(
                        "moon", variant="ghost", size="sm",
                        on_click=ColorScheme.toggle(),
                        tooltip="Passer en sombre", classes="dark:!hidden",
                    )
                    ui.icon_button(
                        "sun", variant="ghost", size="sm",
                        on_click=ColorScheme.toggle(),
                        tooltip="Passer en clair",
                        classes="!hidden dark:!inline-flex",
                    )

            with ui.hstack(justify="between", align="center", gap="sm",
                           wrap=True, classes="px-4 pb-2.5"):
                with ui.hstack(align="center", gap="sm"):
                    # ``debounce`` sur le champ : une requête par pause de
                    # frappe, pas une par caractère. Le filtrage est
                    # SERVEUR ici — cf. ``state.Filtres``, qui dit
                    # pourquoi le filtre client de la messagerie serait un
                    # bug sur un tableau dont on glisse les cartes.
                    ui.input(
                        value=filtres.q, on_input=filtrer, debounce=350,
                        placeholder="Rechercher une carte",
                        icon_left="search", size="sm", clearable=True,
                        classes="w-72",
                    )
                    ui.select(
                        value=filtres.qui, on_change=filtrer, size="sm",
                        classes="w-44",
                        options=[("tous", "Toute l'équipe"),
                                 *[(cle, nom) for cle, nom, _, _ in MEMBRES]],
                    )
                    ui.select(
                        value=filtres.etiquette, on_change=filtrer, size="sm",
                        classes="w-40",
                        options=[("toutes", "Toutes étiquettes"),
                                 *[(cle, lib) for cle, lib, _ in ETIQUETTES]],
                    )
                with ui.hstack(align="center", gap="sm"):
                    commandes()
                    dialogue_nouvelle()

        ui.outlet(classes="flex-1 min-h-0 flex")


feature = Feature(
    name="shell", kind="shell",
    provides=[shell, identite, connexion, dialogue_nouvelle, commandes],
    uses=["donnees", "state", "logic"],
)
