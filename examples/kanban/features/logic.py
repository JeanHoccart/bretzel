"""kanban/logic — the handlers. They mutate the board, the display
follows.

None touches the DOM, none returns HTML: they write into a state, and the
``@refreshable`` zones depending on it re-render — at the author of the
gesture through ``deps=``, at the others through ``broadcast=``.

**Every write goes through :func:`journaliser`.** A card is never
modified in place: we take its snapshot before, build the one after, and
the pair goes to the journal. Three things follow without any being coded
twice — undo, redo, and the activity feed that says who did what.

⚠️ **A collection is REASSIGNED, it is not mutated in place.**
``tableau.cartes[0]["titre"] = "x"`` does write the value but does not
change the list's identity: change detection sees nothing and no zone
re-renders (``traps.md`` § collection mutation). Hence :func:`poser`,
which rebuilds the list around the card touched.
"""

from __future__ import annotations

import time
from typing import Any

from bretzel import Feature, ui
from bretzel.components import Move
from examples.kanban.core.i18n import tr
from examples.kanban.features.donnees import (
    CLES,
    LIB_ETIQUETTE,
    LIMITES,
    NOMS,
    Tableau,
    carte_par_id,
    colonne_de,
    copie,
    entre,
    libelles,
    pleine,
)
from examples.kanban.features.state import (
    Avancement,
    Brouillon,
    Fiche,
    Filtres,
    Moi,
    Nouvelle,
    Vue,
)

#: The drag group. Naming it is what allows a column to receive: each
#: declares ``accepts=[GROUPE]``. Without that, a zone receives only its
#: own cards — receiving from elsewhere is an opt-in.
GROUPE = "carte"

#: The ``name=`` of the banner's archive zone. It accepts everything and
#: lets nothing leave (``locked=True``): it is the case the
#: ``accepts`` / ``locked`` distinction exists to express.
ZONE_ARCHIVE = "archive"


# ── The writing base: place a card, and record it in the journal ─────


def poser(ident: str, etat: dict[str, Any] | None) -> None:
    """Write a card's state: replace it, add it, or remove it.

    ``None`` removes. The order in the list does not matter at all — the
    display sorts by ``rang`` — so reinserting at the end is enough, and
    that is what makes undoing a deletion as simple as a modification.
    """
    tableau = Tableau()
    autres = [c for c in tableau.cartes if c["id"] != ident]
    tableau.cartes = autres if etat is None else [*autres, dict(etat)]


def journaliser(ident: str, avant: dict[str, Any] | None,
                apres: dict[str, Any] | None, texte: str) -> None:
    """Apply a change AND record it in the board's history.

    A new action TRUNCATES what followed the cursor: after three undos,
    writing something abandons the three possible redos. It is the
    behaviour of every undo stack, and the alternative — keeping a branch
    — would need an interface to choose it.
    """
    tableau = Tableau()
    poser(ident, apres)
    tableau.journal = [
        *tableau.journal[: tableau.curseur],
        {"t": time.time(), "qui": Moi().membre, "texte": texte,
         "id": ident, "avant": avant, "apres": apres},
    ]
    tableau.curseur = len(tableau.journal)


def modifier(carte: dict[str, Any], texte: str, **champs: Any) -> None:
    """The common case: change a few fields of an existing card.

    A change that changes nothing does not enter the journal — otherwise
    putting a card back where it was picked up would fill the undo stack
    with gestures that had no effect.
    """
    avant = copie(carte)
    apres = {**avant, **champs}
    if apres == avant:
        return
    journaliser(carte["id"], avant, apres, texte)


def carte_ouverte() -> dict[str, Any] | None:
    """The card shown in the drawer, if it still exists.

    It may have vanished under the reader's eyes — somebody else has
    just archived it. The drawer must then close cleanly, not raise.
    """
    ouverte = Vue().ouverte
    return carte_par_id(ouverte) if ouverte else None


# ── Undo / redo ───────────────────────────────────────────────────────


def annuler() -> None:
    """Undo the board's last write, whoever's hand made it.

    On a shared board, the history belongs to the board: the journal says
    who made the gesture, and anybody can undo it. A stack per person
    would raise the unanswerable question of what the second hand undoes
    when the first has already moved the card again.
    """
    tableau = Tableau()
    if tableau.curseur == 0:
        return
    entree = tableau.journal[tableau.curseur - 1]
    poser(entree["id"], entree["avant"])
    tableau.curseur -= 1
    if Vue().ouverte == entree["id"] and entree["avant"] is None:
        fermer()


def refaire() -> None:
    """Redo what the last undo had undone."""
    tableau = Tableau()
    if tableau.curseur >= len(tableau.journal):
        return
    entree = tableau.journal[tableau.curseur]
    poser(entree["id"], entree["apres"])
    tableau.curseur += 1
    if Vue().ouverte == entree["id"] and entree["apres"] is None:
        fermer()


# ── Drag and drop ─────────────────────────────────────────────────────


def deposer(m: Move) -> None:
    """What a drop applies — or refuses.

    **Refusing is mutating nothing.** The browser has already moved the
    card by the time this code runs; a server render that contradicts it
    puts it back through the morph. So there is no ``reject()`` to call,
    and that is why the work-in-progress limit is written in three lines.

    The neighbours are re-read INSIDE THE FILTERED WINDOW, with the
    function that served the rendering. Computing a rank between two
    cards the reader could not see would drop the card somewhere other
    than under their finger, without the slightest error to say so.
    """
    carte = carte_par_id(m.item_key)
    if carte is None or m.to_zone not in CLES:
        return

    transfert = m.to_zone != carte["colonne"]
    if transfert and pleine(m.to_zone):
        ui.notification(
            tr(f"“{libelles()[m.to_zone]}” is at its limit of "
               f"{LIMITES[m.to_zone]} cards. One has to come out before "
               f"another is accepted.",
               f"« {libelles()[m.to_zone]} » est à sa limite de "
               f"{LIMITES[m.to_zone]} cartes. Il faut en sortir une avant "
               f"d'en accepter une autre."),
            variant="warning", duration_ms=4000,
            title=tr("Drop refused", "Dépôt refusé"),
        )
        return

    filtres = Filtres()
    voisins = [
        c for c in colonne_de(m.to_zone, filtres.qui, filtres.etiquette,
                              filtres.q)
        if c["id"] != carte["id"]
    ]
    place = max(0, min(m.to_index, len(voisins)))
    rang = entre(
        voisins[place - 1]["rang"] if place > 0 else None,
        voisins[place]["rang"] if place < len(voisins) else None,
    )
    verbe = (
        tr(f"moved “{carte['titre']}” to {libelles()[m.to_zone]}",
           f"a déplacé « {carte['titre']} » vers {libelles()[m.to_zone]}")
        if transfert else
        tr(f"reordered “{carte['titre']}”",
           f"a réordonné « {carte['titre']} »")
    )
    modifier(carte, verbe, colonne=m.to_zone, rang=rang)


def sortir(carte: dict[str, Any]) -> None:
    """Remove a card from the board, whichever gesture said so."""
    if Vue().ouverte == carte["id"]:
        fermer()
    journaliser(carte["id"], copie(carte), None,
                tr(f"archived “{carte['titre']}”",
                   f"a archivé « {carte['titre']} »"))


def archiver(m: Move) -> None:
    """Take a card out by dropping it on the banner's archive zone."""
    carte = carte_par_id(m.item_key)
    if carte is not None:
        sortir(carte)


def archiver_ouverte() -> None:
    """The same gesture, from the drawer's button.

    Two paths for one action, and it is intended: dragging to the archive
    is the natural gesture when the card is in hand, but it does not
    exist for whoever is reading the open card — and it does not exist
    from the keyboard either.
    """
    carte = carte_ouverte()
    if carte is not None:
        sortir(carte)


# ── The drawer: open, and copy the card into the draft ───────────────


def charger(carte: dict[str, Any]) -> None:
    """Copy the card into the editing draft.

    The server writes a ``ClientState``: the value comes back down in the
    response's patch, like composing a reply in ``examples/messagerie``.
    That is what lets the draft be seeded by the server AND survive a
    re-render coming from elsewhere.
    """
    Fiche().carte_id = carte["id"]
    brouillon = Brouillon()
    brouillon.titre = carte["titre"]
    brouillon.description = carte["description"]
    brouillon.qui = carte["qui"]
    brouillon.echeance = carte["echeance"]
    brouillon.points = carte["points"]
    brouillon.sous_tache = ""
    brouillon.commentaire = ""
    Avancement().faites = sum(
        1 for s in carte["sous_taches"] if s["fait"])


def ouvrir(ident: str) -> None:
    """Show a card in the drawer, draft reloaded."""
    carte = carte_par_id(ident)
    if carte is None:
        return
    vue = Vue()
    vue.ouverte = ident
    vue.tiroir = True
    charger(carte)


def fermer() -> None:
    """Close the drawer — both fields together, always.

    Wired on the drawer's ``on_close`` too: closing with Escape or by
    clicking the backdrop must be known server side, otherwise the next
    re-render would reopen the panel.
    """
    vue = Vue()
    vue.ouverte = ""
    vue.tiroir = False


def enregistrer() -> None:
    """Write the draft's free fields onto the card.

    ⚠️ No typed parameter, and it is NOT the carelessness rule B1 of
    ``livrer-une-app.md`` forbids: a typed parameter serves to hydrate a
    SERVER state from the POST body. The draft is a ``ClientState`` — the
    browser's store travels with every action, so ``Brouillon()`` already
    returns fresh values.

    ``Fiche().carte_id`` rather than ``Vue().ouverte``: the sheet says
    which card the draft belongs to, so a save that left while another
    one was being opened cannot write on the wrong one.
    """
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    titre = str(brouillon.titre).strip()[:120]
    if carte is None or not titre:
        return
    qui = str(brouillon.qui)
    modifier(
        carte, tr(f"edited “{carte['titre']}”",
                  f"a modifié « {carte['titre']} »"),
        titre=titre,
        description=str(brouillon.description).strip()[:800],
        qui=qui if qui in NOMS else carte["qui"],
        echeance=str(brouillon.echeance)[:10],
        points=max(0, min(99, int(brouillon.points or 0))),
    )


def basculer_etiquette(cle: str) -> None:
    """Set or remove a label on the open card."""
    carte = carte_ouverte()
    if carte is None or cle not in LIB_ETIQUETTE:
        return
    posees = list(carte["etiquettes"])
    if cle in posees:
        posees.remove(cle)
        verbe = tr(f"removed the {LIB_ETIQUETTE[cle]} label",
                   f"a retiré l'étiquette {LIB_ETIQUETTE[cle]}")
    else:
        posees.append(cle)
        verbe = tr(f"set the {LIB_ETIQUETTE[cle]} label",
                   f"a posé l'étiquette {LIB_ETIQUETTE[cle]}")
    modifier(carte,
             tr(f"{verbe} on “{carte['titre']}”",
                f"{verbe} sur « {carte['titre']} »"),
             etiquettes=posees)


# ── Subtasks and comments: on click, with no "save" ──────────────────


def ajouter_sous_tache() -> None:
    """One more subtask, taken from the drawer's field."""
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    texte = str(brouillon.sous_tache).strip()[:120]
    if carte is None or not texte:
        return
    modifier(carte,
             tr(f"added “{texte}” to “{carte['titre']}”",
                f"a ajouté « {texte} » à « {carte['titre']} »"),
             sous_taches=[*[dict(s) for s in carte["sous_taches"]],
                          {"texte": texte, "fait": False}])
    brouillon.sous_tache = ""


def basculer_sous_tache(rang: int) -> None:
    """Tick or untick subtask number ``rang``."""
    carte = carte_ouverte()
    if carte is None or not 0 <= rang < len(carte["sous_taches"]):
        return
    sous = [dict(s) for s in carte["sous_taches"]]
    sous[rang]["fait"] = not sous[rang]["fait"]
    fait = sous[rang]["fait"]
    etat = tr("done" if fait else "to do again",
              "faite" if fait else "à refaire")
    modifier(carte,
             tr(f"marked “{sous[rang]['texte']}” {etat}",
                f"a marqué « {sous[rang]['texte']} » {etat}"),
             sous_taches=sous)


def retirer_sous_tache(rang: int) -> None:
    """Delete subtask number ``rang``."""
    carte = carte_ouverte()
    if carte is None or not 0 <= rang < len(carte["sous_taches"]):
        return
    sous = [dict(s) for i, s in enumerate(carte["sous_taches"]) if i != rang]
    modifier(carte,
             tr(f"removed a subtask from “{carte['titre']}”",
                f"a retiré une sous-tâche de « {carte['titre']} »"),
             sous_taches=sous)


def commenter() -> None:
    """Add a comment signed with the current identity."""
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    texte = str(brouillon.commentaire).strip()[:600]
    if carte is None or not texte:
        return
    modifier(carte,
             tr(f"commented on “{carte['titre']}”",
                f"a commenté « {carte['titre']} »"),
             commentaires=[*[dict(c) for c in carte["commentaires"]],
                           {"qui": Moi().membre, "texte": texte,
                            "t": time.time()}])
    brouillon.commentaire = ""


# ── Create, and the banner's controls ────────────────────────────────


def identifiant_libre() -> str:
    """The next card identifier, derived from the largest existing one.

    A stored counter would be a second state to keep consistent with the
    list; deriving it cannot drift.
    """
    nombres = [
        int(c["id"][1:]) for c in Tableau().cartes
        if c["id"][:1] == "c" and c["id"][1:].isdigit()
    ]
    return f"c{max(nombres, default=0) + 1:02d}"


def creer(nouvelle: Nouvelle) -> None:
    """A new card, at the head of the chosen column, and we open it."""
    titre = str(nouvelle.titre).strip()[:120]
    colonne = str(nouvelle.colonne)
    if not titre:
        return
    if pleine(colonne):
        ui.notification(
            tr(f"“{libelles()[colonne]}” is at its limit of "
               f"{LIMITES[colonne]} cards.",
               f"« {libelles()[colonne]} » est à sa limite de "
               f"{LIMITES[colonne]} cartes."),
            variant="warning", duration_ms=4000,
            title=tr("Creation refused", "Création refusée"),
        )
        return
    premieres = colonne_de(colonne)
    ident = identifiant_libre()
    neuve = {
        "id": ident, "colonne": colonne, "titre": titre,
        "qui": Moi().membre, "etiquettes": [], "echeance": "", "points": 0,
        "description": "", "sous_taches": [], "commentaires": [],
        "rang": entre(None, premieres[0]["rang"] if premieres else None),
    }
    journaliser(ident, None, neuve,
                tr(f"created “{titre}”", f"a créé « {titre} »"))
    nouvelle.titre = ""
    ouvrir(ident)


def filtrer(filtres: Filtres) -> None:
    """Nothing to do: the control's value is hydrated, ``deps=`` follows.

    ⚠️ **The typed parameter is not decorative — it is what HYDRATES.**
    Written ``def filtrer()`` with no parameter, the handler fires, does
    not raise, and the server answers zero bytes: it read no value, so no
    state changed, so no zone is to be re-rendered. The three filters
    were inert and nothing said so — measured by probe, invisible when
    reading.
    """


def changer_de_membre(moi: Moi) -> None:
    """``Moi.membre`` is hydrated by the selector; nothing else to do.

    No authentication here, and it is written down: this example stages
    shared state, not identity — ``examples/auth`` does the other one.
    :class:`Moi`'s validator pulls any unknown value back, so this
    handler has nothing to check.
    """


feature = Feature(
    name="logic", kind="logic",
    provides=[poser, journaliser, modifier, carte_ouverte, annuler, refaire,
              deposer, sortir, archiver, archiver_ouverte, charger, ouvrir,
              fermer, enregistrer, basculer_etiquette, ajouter_sous_tache,
              basculer_sous_tache, retirer_sous_tache, commenter,
              identifiant_libre, creer, filtrer, changer_de_membre],
    uses=["donnees", "state"],
)
