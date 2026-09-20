"""kanban/fiche — a card's detail drawer.

A ``ui.drawer`` whose openness is a FUNCTION of the state: it is open if,
and only if, ``Vue().ouverte`` names a card that still exists. Nothing
else opens it and nothing else closes it — and that is what makes a card
archived by somebody else close the drawer of whoever was looking at it,
cleanly.

**Two writing regimes, and the difference shows on screen.** The title
and the description are typed: saving them at every keystroke would
write into a state three other people are watching, so they wait for
"Enregistrer". The labels, the subtasks and the comments leave on the
click, because a click IS already the decision.
"""

from __future__ import annotations

from functools import partial

from bretzel import refreshable, ui
from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    COULEURS,
    ETIQUETTES,
    INITIALES,
    MEMBRES,
    NOMS,
    Tableau,
    avancement,
    carte_par_id,
    depuis,
    libelles,
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
    """The draft: what gets typed, and the button that saves it."""
    with ui.form(on_submit=enregistrer), ui.vstack(gap="sm"):
        with ui.form_field(label=tr("Title", "Titre"), required=True):
            ui.input(value=brouillon.titre, maxlength=120, size="sm",
                     placeholder=tr("The card's title", "Titre de la carte"))
        with ui.form_field(label=tr("Description", "Description")):
            ui.textarea(value=brouillon.description, rows=4, maxlength=800,
                        size="sm",
                        placeholder=tr("What one needs to know to take it",
                                       "Ce qu'il faut savoir pour la "
                                       "prendre"))
        # ⚠️ Two columns and not three. At three, the date picker falls
        # below 120 px and its value is CUT — "2026-09" instead of the
        # whole date, without the slightest overflow to signal it.
        # Measured on a screenshot, invisible when reading the code.
        with ui.form_field(label=tr("Assignee", "Assigné")):
            ui.select(value=brouillon.qui, size="sm",
                      options=[(cle, nom) for cle, nom, _, _ in MEMBRES])
        with ui.grid(cols={"base": 1, "sm": 2}, gap="sm"):
            with ui.form_field(label=tr("Due date", "Échéance")):
                ui.date_picker(value=brouillon.echeance, size="sm")
            with ui.form_field(label=tr("Points", "Points")):
                ui.number_input(value=brouillon.points, min=0, max=99, size="sm")
        with ui.hstack(justify="end"):
            ui.button(tr("Save", "Enregistrer"), type="submit",
                      color="primary", size="sm", icon_left="check")


def etiquettes(carte: dict) -> None:
    """The five labels, set or removed on click.

    One button per label rather than a ``select multiple``: the
    set/unset state must read at a glance, and setting the third must not
    reopen a menu.
    """
    with ui.vstack(gap="xs"):
        ui.text(tr("Labels", "Étiquettes"), size="xs", weight="medium",
                color="muted")
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
    """The checklist, its progress bar, and the add field."""
    faites, total = avancement(carte)
    # ⚠️ **Re-seed at EVERY render, not only on opening.** The counter
    # is optimistic: it advances in the browser before the request
    # leaves. This line is the "reconcile" half — it puts back the
    # server's value, which is authoritative, including when it is
    # somebody ELSE who ticked. Without it, a box ticked on the other
    # side of the world would move the list and not the bar.
    #
    # ⚠️ And it is for THIS line that ``Avancement`` is a separate class:
    # writing one client-state value from the server sends the WHOLE
    # object back in the patch. As long as the counter lived in
    # ``Brouillon``, reconciling here also put the comment being typed
    # back to what the server believed — that is, empty.
    Avancement().faites = faites
    with ui.vstack(gap="xs"):
        with ui.hstack(justify="between", align="center"):
            ui.text(tr("Subtasks", "Sous-tâches"), size="xs",
                    weight="medium", color="muted")
            if total:
                # Two ``ui.text`` and not one f-string: an f-string
                # around a binding RAISES, and it is a guard rail — it
                # would freeze the value at render time. The first
                # follows the client counter, the second is constant.
                with ui.hstack(gap="none", align="center"):
                    ui.text(Avancement().faites, size="xs", color="muted")
                    ui.text(tr(f" of {total}", f" sur {total}"),
                            size="xs", color="muted")
        if total:
            # ``value=`` is a BOUND prop: the bar moves on click, with
            # no round trip. ``color=`` stays server side — a class does
            # not bind on the client, so the green of "all done" arrives
            # with the response.
            ui.progress(value=Avancement().faites, max=total,
                        color="success" if faites == total else "primary",
                        size="sm")
        for rang, sous in enumerate(carte["sous_taches"]):
            with ui.hstack(gap="sm", align="center"):
                # ⚠️ ``label=`` on the box, and not a ``ui.text``
                # beside it. A box's ``<input>`` is ``sr-only``: it is
                # its drawn box that receives the click, so text placed
                # as a neighbour is NOT a target — and on a touch screen
                # the useful area drops to 16 px a side.
                # Two effects for one click: the server writes the
                # truth, and the client counter moves at once. The
                # DIRECTION is decided at render time — a ticked box can
                # only untick — and the reconciliation above catches the
                # case where the server disagrees.
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
                               tooltip=tr("Remove this subtask",
                                          "Retirer cette sous-tâche"))
        with ui.form(on_submit=ajouter_sous_tache), ui.hstack(gap="xs", align="center"):
            ui.input(value=brouillon.sous_tache, size="sm", maxlength=120,
                     placeholder=tr("Add a subtask",
                                    "Ajouter une sous-tâche"),
                     classes="flex-1")
            ui.icon_button("plus", type="submit", variant="soft",
                           size="sm", tooltip=tr("Add", "Ajouter"))


def commentaires(carte: dict, brouillon: Brouillon) -> None:
    """The card's discussion thread, and the writing field."""
    with ui.vstack(gap="sm"):
        ui.text(tr("Comments", "Commentaires"), size="xs",
                weight="medium", color="muted")
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
                        placeholder=tr("Write a comment",
                                       "Écrire un commentaire"))
            with ui.hstack(justify="end"):
                ui.button(tr("Comment", "Commenter"), type="submit",
                          variant="soft", size="sm",
                          icon_left="message-circle")


@refreshable(deps=[Tableau, Vue], broadcast=[Tableau])
def tiroir() -> None:
    """The drawer, opened by the state and not by a click.

    ``broadcast=[Tableau]``: if somebody else ticks a subtask of the card
    I am looking at, the tick moves before my eyes.

    The draft is only reloaded if the drawer changes card. Without that
    guard, every re-render — so every gesture by anybody — would
    overwrite the title being typed with the server's.

    ⚠️ **That guard was not enough**, and it is what moved the fields to
    ``ClientState``. It stops the server REWRITING the draft; it did not
    stop the zone's re-render replacing the ``<input>`` with the
    server's. Measured across two sessions: A drags a card, and four
    seconds later the comment B was typing is empty.
    """
    vue = Vue()
    carte = carte_par_id(vue.ouverte) if vue.ouverte else None
    brouillon = Brouillon()
    if carte is not None and Fiche().carte_id != carte["id"]:
        charger(carte)

    with ui.drawer(open=vue.tiroir, side="right", width="lg",
                   title=(carte["titre"] if carte
                          else tr("Card", "Carte")),
                   on_close=fermer):
        if carte is None:
            return
        with ui.vstack(gap="md"):
            with ui.hstack(gap="xs", align="center"):
                ui.badge(libelles()[carte["colonne"]], size="xs",
                         variant="soft", color="primary")
                ui.text(tr(f"Card {carte['id']}", f"Carte {carte['id']}"),
                        size="xs", color="muted")
            champs(brouillon)
            ui.divider()
            etiquettes(carte)
            ui.divider()
            sous_taches(carte, brouillon)
            ui.divider()
            commentaires(carte, brouillon)
            ui.divider()
            with ui.hstack(justify="end"):
                ui.button(tr("Archive this card",
                             "Archiver cette carte"),
                          variant="ghost", color="error", size="sm",
                          icon_left="archive", on_click=archiver_ouverte)
