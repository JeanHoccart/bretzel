"""kanban/fiche — le tiroir de détail d'une carte.

Un ``ui.drawer`` dont l'ouverture est une FONCTION de l'état : il est
ouvert si, et seulement si, ``Vue().ouverte`` désigne une carte qui
existe encore. Rien d'autre ne l'ouvre et rien d'autre ne le ferme — et
c'est ce qui fait qu'une carte archivée par quelqu'un d'autre referme
proprement le tiroir de celui qui la regardait.

**Deux régimes d'écriture, et la différence se voit à l'écran.** Le titre
et la description se tapent : les enregistrer à chaque frappe écrirait
dans un état que trois autres personnes regardent, donc ils attendent
« Enregistrer ». Les étiquettes, les sous-tâches et les commentaires
partent au clic, parce qu'un clic EST déjà la décision.
"""

from __future__ import annotations

from functools import partial

from bretzel import refreshable, ui
from examples.kanban.features.donnees import (
    COULEURS,
    ETIQUETTES,
    INITIALES,
    LIBELLES,
    MEMBRES,
    NOMS,
    Tableau,
    avancement,
    carte_par_id,
    depuis,
)
from examples.kanban.features.logic import (
    ajouter_sous_tache,
    archiver_ouverte,
    basculer_etiquette,
    basculer_sous_tache,
    charger,
    commenter,
    enregistrer,
    fermer,
    retirer_sous_tache,
)
from examples.kanban.features.state import (
    Avancement,
    Brouillon,
    Fiche,
    Vue,
)


def champs(brouillon: Brouillon) -> None:
    """Le brouillon : ce qui se tape, et le bouton qui l'enregistre."""
    with ui.form(on_submit=enregistrer), ui.vstack(gap="sm"):
        with ui.form_field(label="Titre", required=True):
            ui.input(value=brouillon.titre, maxlength=120, size="sm",
                     placeholder="Titre de la carte")
        with ui.form_field(label="Description"):
            ui.textarea(value=brouillon.description, rows=4, maxlength=800,
                        size="sm",
                        placeholder="Ce qu'il faut savoir pour la prendre")
        # ⚠️ Deux colonnes et pas trois. À trois, le sélecteur de dates
        # tombe sous 120 px et sa valeur est COUPÉE — « 2026-09 » au lieu
        # de la date entière, sans le moindre débordement pour le
        # signaler. Mesuré à la capture, invisible à la lecture du code.
        with ui.form_field(label="Assigné"):
            ui.select(value=brouillon.qui, size="sm",
                      options=[(cle, nom) for cle, nom, _, _ in MEMBRES])
        with ui.grid(cols={"base": 1, "sm": 2}, gap="sm"):
            with ui.form_field(label="Échéance"):
                ui.date_picker(value=brouillon.echeance, size="sm")
            with ui.form_field(label="Points"):
                ui.number_input(value=brouillon.points, min=0, max=99, size="sm")
        with ui.hstack(justify="end"):
            ui.button("Enregistrer", type="submit", color="primary",
                      size="sm", icon_left="check")


def etiquettes(carte: dict) -> None:
    """Les cinq étiquettes, posées ou retirées au clic.

    Un bouton par étiquette plutôt qu'un ``select multiple`` : l'état
    posé/non posé doit se lire d'un coup d'œil, et poser la troisième ne
    doit pas rouvrir un menu.
    """
    with ui.vstack(gap="xs"):
        ui.text("Étiquettes", size="xs", weight="medium", color="muted")
        with ui.hstack(gap="xs", wrap=True):
            for cle, libelle, couleur in ETIQUETTES:
                posee = cle in carte["etiquettes"]
                ui.button(
                    libelle, size="xs", color=couleur if posee else "muted",
                    variant="soft" if posee else "ghost",
                    icon_left="check" if posee else "plus",
                    on_click=partial(basculer_etiquette, cle),
                )


def sous_taches(carte: dict, brouillon: Brouillon) -> None:
    """La liste à cocher, sa barre d'avancement, et le champ d'ajout."""
    faites, total = avancement(carte)
    # ⚠️ **Réamorcer à CHAQUE rendu, pas seulement à l'ouverture.** Le
    # compteur est optimiste : il avance dans le navigateur avant que la
    # requête parte. Cette ligne est la moitié « réconcilier » — elle
    # remet la valeur du serveur, qui fait foi, y compris quand c'est
    # quelqu'un d'AUTRE qui a coché. Sans elle, une case cochée à l'autre
    # bout du monde bougerait la liste et pas la barre.
    #
    # ⚠️ Et c'est pour CETTE ligne qu'``Avancement`` est une classe à
    # part : écrire une valeur d'état client depuis le serveur renvoie
    # l'objet ENTIER dans le patch. Tant que le compteur vivait dans
    # ``Brouillon``, réconcilier ici remettait aussi le commentaire en
    # cours de frappe à ce que le serveur croyait — c'est-à-dire vide.
    Avancement().faites = faites
    with ui.vstack(gap="xs"):
        with ui.hstack(justify="between", align="center"):
            ui.text("Sous-tâches", size="xs", weight="medium", color="muted")
            if total:
                # Deux ``ui.text`` et pas une f-string : une f-string
                # autour d'un binding LÈVE, et c'est un garde-fou — elle
                # figerait la valeur au rendu. Le premier suit le
                # compteur client, le second est constant.
                with ui.hstack(gap="none", align="center"):
                    ui.text(Avancement().faites, size="xs", color="muted")
                    ui.text(f" sur {total}", size="xs", color="muted")
        if total:
            # ``value=`` est une prop LIÉE : la barre bouge au clic, sans
            # aller-retour. ``color=`` reste serveur — une classe ne se
            # lie pas côté client, donc le vert de « tout est fait »
            # arrive avec la réponse.
            ui.progress(value=Avancement().faites, max=total,
                        color="success" if faites == total else "primary",
                        size="sm")
        for rang, sous in enumerate(carte["sous_taches"]):
            with ui.hstack(gap="sm", align="center"):
                # ⚠️ ``label=`` sur la case, et pas un ``ui.text`` à côté.
                # L'``<input>`` d'une case est ``sr-only`` : c'est sa boîte
                # dessinée qui reçoit le clic, donc un texte posé en
                # voisin n'est PAS une cible — et sur un écran tactile la
                # zone utile tombe à 16 px de côté.
                # Deux effets pour un clic : le serveur écrit la
                # vérité, et le compteur client bouge tout de suite. Le
                # SENS est décidé au rendu — une case cochée ne peut que
                # se décocher — et la réconciliation ci-dessus rattrape
                # le cas où le serveur n'est pas d'accord.
                ui.checkbox(checked=sous["fait"], size="sm",
                            label=sous["texte"],
                            on_change=[
                                partial(basculer_sous_tache, rang),
                                Avancement().faites.decrement(1) if sous["fait"]
                                else Avancement().faites.increment(1),
                            ],
                            classes="flex-1 min-w-0")
                ui.icon_button("x", variant="ghost", size="xs", color="muted",
                               on_click=partial(retirer_sous_tache, rang),
                               tooltip="Retirer cette sous-tâche")
        with ui.form(on_submit=ajouter_sous_tache), ui.hstack(gap="xs", align="center"):
            ui.input(value=brouillon.sous_tache, size="sm", maxlength=120,
                     placeholder="Ajouter une sous-tâche",
                     classes="flex-1")
            ui.icon_button("plus", type="submit", variant="soft",
                           size="sm", tooltip="Ajouter")


def commentaires(carte: dict, brouillon: Brouillon) -> None:
    """Le fil de discussion de la carte, et le champ d'écriture."""
    with ui.vstack(gap="sm"):
        ui.text("Commentaires", size="xs", weight="medium", color="muted")
        for mot in carte["commentaires"]:
            with ui.hstack(gap="sm", align="start"):
                ui.avatar(initials=INITIALES[mot["qui"]], size="xs",
                          color=COULEURS[mot["qui"]])
                with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                    with ui.hstack(gap="xs", align="center"):
                        ui.text(NOMS[mot["qui"]], size="xs", weight="medium")
                        ui.text(depuis(mot["t"]), size="xs", color="muted")
                    ui.text(mot["texte"], size="sm")
        with ui.form(on_submit=commenter), ui.vstack(gap="xs"):
            ui.textarea(value=brouillon.commentaire, rows=2, maxlength=600,
                        placeholder="Écrire un commentaire")
            with ui.hstack(justify="end"):
                ui.button("Commenter", type="submit", variant="soft",
                          size="sm", icon_left="message-circle")


@refreshable(deps=[Tableau, Vue], broadcast=[Tableau])
def tiroir() -> None:
    """Le tiroir, ouvert par l'état et pas par un clic.

    ``broadcast=[Tableau]`` : si quelqu'un d'autre coche une sous-tâche
    de la carte que je regarde, la coche bouge sous mes yeux.

    Le brouillon n'est rechargé que si le tiroir change de carte. Sans
    cette garde, chaque re-rendu — donc chaque geste de n'importe qui —
    écraserait le titre en cours de frappe par celui du serveur.

    ⚠️ **Cette garde ne suffisait pas**, et c'est ce qui a fait passer
    les champs en ``ClientState``. Elle empêche le serveur de RÉÉCRIRE le
    brouillon ; elle n'empêchait pas le re-rendu de la zone de remplacer
    les ``<input>`` par ceux du serveur. Mesuré à deux sessions : A glisse
    une carte, et quatre secondes plus tard le commentaire que B tapait
    est vide.
    """
    vue = Vue()
    carte = carte_par_id(vue.ouverte) if vue.ouverte else None
    brouillon = Brouillon()
    if carte is not None and Fiche().carte_id != carte["id"]:
        charger(carte)

    with ui.drawer(open=vue.tiroir, side="right", width="lg",
                   title=carte["titre"] if carte else "Carte",
                   on_close=fermer):
        if carte is None:
            return
        with ui.vstack(gap="md"):
            with ui.hstack(gap="xs", align="center"):
                ui.badge(LIBELLES[carte["colonne"]], size="xs",
                         variant="soft", color="primary")
                ui.text(f"Carte {carte['id']}", size="xs", color="muted")
            champs(brouillon)
            ui.divider()
            etiquettes(carte)
            ui.divider()
            sous_taches(carte, brouillon)
            ui.divider()
            commentaires(carte, brouillon)
            ui.divider()
            with ui.hstack(justify="end"):
                ui.button("Archiver cette carte", variant="ghost",
                          color="error", size="sm", icon_left="archive",
                          on_click=archiver_ouverte)
