"""kanban/logic — les handlers. Ils mutent le tableau, l'affichage suit.

Aucun ne touche au DOM, aucun ne rend de HTML : ils écrivent dans un
état, et les zones ``@refreshable`` qui en dépendent se re-rendent — chez
l'auteur du geste par ``deps=``, chez les autres par ``broadcast=``.

**Toute écriture passe par :func:`journaliser`.** Une carte n'est jamais
modifiée sur place : on prend son instantané avant, on construit celui
d'après, et le couple part au journal. Trois choses en découlent sans
qu'aucune soit codée deux fois — l'annulation, le rétablissement, et le
fil d'activité qui dit qui a fait quoi.

⚠️ **Une collection se RÉASSIGNE, elle ne se mute pas en place.**
``tableau.cartes[0]["titre"] = "x"`` écrit bien la valeur mais ne change
pas l'identité de la liste : la détection de changement ne voit rien et
aucune zone ne se re-rend (``traps.md`` § mutation de collection). D'où
:func:`poser`, qui rebâtit la liste autour de la carte touchée.
"""

from __future__ import annotations

import time
from typing import Any

from bretzel import Feature, ui
from bretzel.components import Move
from examples.kanban.features.donnees import (
    CLES,
    LIB_ETIQUETTE,
    LIBELLES,
    LIMITES,
    NOMS,
    Tableau,
    carte_par_id,
    colonne_de,
    copie,
    entre,
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

#: Le groupe de glissement. Le nommer est ce qui autorise une colonne à
#: recevoir : chacune déclare ``accepts=[GROUPE]``. Sans ça, une zone ne
#: reçoit que ses propres cartes — recevoir d'ailleurs est un opt-in.
GROUPE = "carte"

#: Le ``name=`` de la zone d'archivage du bandeau. Elle accepte tout et
#: ne laisse rien repartir (``locked=True``) : c'est le cas que la
#: distinction ``accepts`` / ``locked`` existe pour exprimer.
ZONE_ARCHIVE = "archive"


# ── Le socle d'écriture : poser une carte, et l'inscrire au journal ───


def poser(ident: str, etat: dict[str, Any] | None) -> None:
    """Écrire l'état d'une carte : la remplacer, l'ajouter, ou la retirer.

    ``None`` retire. L'ordre dans la liste n'a aucune importance —
    l'affichage trie par ``rang`` — donc réinsérer en fin suffit, et
    c'est ce qui rend l'annulation d'une suppression aussi simple qu'une
    modification.
    """
    tableau = Tableau()
    autres = [c for c in tableau.cartes if c["id"] != ident]
    tableau.cartes = autres if etat is None else [*autres, dict(etat)]


def journaliser(ident: str, avant: dict[str, Any] | None,
                apres: dict[str, Any] | None, texte: str) -> None:
    """Appliquer un changement ET l'inscrire dans l'histoire du tableau.

    Une action neuve TRONQUE ce qui suivait le curseur : après trois
    annulations, écrire quelque chose abandonne les trois rétablissements
    possibles. C'est le comportement de toutes les piles d'annulation, et
    l'alternative — garder une branche — demanderait une interface pour
    la choisir.
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
    """Le cas courant : changer quelques champs d'une carte existante.

    Un changement qui ne change rien n'entre pas au journal — sans quoi
    reposer une carte à l'endroit où on l'a prise remplirait la pile
    d'annulations de gestes sans effet.
    """
    avant = copie(carte)
    apres = {**avant, **champs}
    if apres == avant:
        return
    journaliser(carte["id"], avant, apres, texte)


def carte_ouverte() -> dict[str, Any] | None:
    """La carte affichée dans le tiroir, si elle existe encore.

    Elle peut avoir disparu sous les yeux du lecteur — quelqu'un d'autre
    vient de l'archiver. Le tiroir doit alors se fermer proprement, pas
    lever.
    """
    ouverte = Vue().ouverte
    return carte_par_id(ouverte) if ouverte else None


# ── Annuler / rétablir ────────────────────────────────────────────────


def annuler() -> None:
    """Défaire la dernière écriture du tableau, quelle qu'en soit la main.

    Sur un tableau partagé, l'histoire appartient au tableau : le journal
    dit qui avait fait le geste, et n'importe qui peut le défaire. Une
    pile par personne poserait la question sans réponse de ce qu'annule
    la seconde main quand la première a déjà redéplacé la carte.
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
    """Refaire ce que la dernière annulation avait défait."""
    tableau = Tableau()
    if tableau.curseur >= len(tableau.journal):
        return
    entree = tableau.journal[tableau.curseur]
    poser(entree["id"], entree["apres"])
    tableau.curseur += 1
    if Vue().ouverte == entree["id"] and entree["apres"] is None:
        fermer()


# ── Le glisser-déposer ────────────────────────────────────────────────


def deposer(m: Move) -> None:
    """Ce qu'un dépôt applique — ou refuse.

    **Refuser, c'est ne rien muter.** Le navigateur a déjà bougé la carte
    quand ce code s'exécute ; un rendu serveur qui le contredit la remet
    en place par le morph. Il n'y a donc pas de ``reject()`` à appeler, et
    c'est pour ça que la limite d'en-cours s'écrit en trois lignes.

    Les voisins sont relus DANS LA FENÊTRE FILTRÉE, avec la fonction qui a
    servi au rendu. Calculer un rang entre deux cartes que le lecteur ne
    voyait pas déposerait la carte ailleurs que sous son doigt, sans la
    moindre erreur pour le dire.
    """
    carte = carte_par_id(m.item_key)
    if carte is None or m.to_zone not in CLES:
        return

    transfert = m.to_zone != carte["colonne"]
    if transfert and pleine(m.to_zone):
        ui.notification(
            f"« {LIBELLES[m.to_zone]} » est à sa limite de "
            f"{LIMITES[m.to_zone]} cartes. Il faut en sortir une avant "
            f"d'en accepter une autre.",
            variant="warning", title="Dépôt refusé", duration_ms=4000,
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
    verbe = (f"a déplacé « {carte['titre']} » vers {LIBELLES[m.to_zone]}"
             if transfert else f"a réordonné « {carte['titre']} »")
    modifier(carte, verbe, colonne=m.to_zone, rang=rang)


def sortir(carte: dict[str, Any]) -> None:
    """Retirer une carte du tableau, quel que soit le geste qui l'a dit."""
    if Vue().ouverte == carte["id"]:
        fermer()
    journaliser(carte["id"], copie(carte), None,
                f"a archivé « {carte['titre']} »")


def archiver(m: Move) -> None:
    """Sortir une carte en la lâchant sur la zone d'archive du bandeau."""
    carte = carte_par_id(m.item_key)
    if carte is not None:
        sortir(carte)


def archiver_ouverte() -> None:
    """Le même geste, au bouton du tiroir.

    Deux chemins pour une action, et c'est voulu : glisser vers
    l'archive est le geste naturel quand on a la carte en main, mais il
    n'existe pas pour qui lit la carte ouverte — et il n'existe pas non
    plus au clavier.
    """
    carte = carte_ouverte()
    if carte is not None:
        sortir(carte)


# ── Le tiroir : ouvrir, et recopier la carte dans le brouillon ────────


def charger(carte: dict[str, Any]) -> None:
    """Recopier la carte dans le brouillon d'édition.

    Le serveur écrit un ``ClientState`` : la valeur redescend dans le
    patch de la réponse, comme la rédaction d'une réponse dans
    ``examples/messagerie``. C'est ce qui permet au brouillon d'être
    amorcé par le serveur ET de survivre à un re-rendu venu d'ailleurs.
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
    """Afficher une carte dans le tiroir, brouillon rechargé."""
    carte = carte_par_id(ident)
    if carte is None:
        return
    vue = Vue()
    vue.ouverte = ident
    vue.tiroir = True
    charger(carte)


def fermer() -> None:
    """Refermer le tiroir — les deux champs ensemble, toujours.

    Câblé aussi sur ``on_close`` du tiroir : fermer à l'échappement ou en
    cliquant le fond doit se savoir côté serveur, sinon le prochain
    re-rendu rouvrirait le panneau.
    """
    vue = Vue()
    vue.ouverte = ""
    vue.tiroir = False


def enregistrer() -> None:
    """Écrire les champs libres du brouillon sur la carte.

    ⚠️ Aucun paramètre typé, et ce n'est PAS l'étourderie que la règle B1
    de ``livrer-une-app.md`` interdit : un paramètre typé sert à hydrater
    un état SERVEUR depuis le corps du POST. Le brouillon est un
    ``ClientState`` — le magasin du navigateur voyage avec chaque action,
    donc ``Brouillon()`` rend déjà des valeurs fraîches.

    ``Fiche().carte_id`` plutôt que ``Vue().ouverte`` : la fiche dit à
    quelle carte le brouillon appartient, donc un enregistrement parti
    pendant qu'on en ouvrait une autre ne peut pas écrire sur la mauvaise.
    """
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    titre = str(brouillon.titre).strip()[:120]
    if carte is None or not titre:
        return
    qui = str(brouillon.qui)
    modifier(
        carte, f"a modifié « {carte['titre']} »",
        titre=titre,
        description=str(brouillon.description).strip()[:800],
        qui=qui if qui in NOMS else carte["qui"],
        echeance=str(brouillon.echeance)[:10],
        points=max(0, min(99, int(brouillon.points or 0))),
    )


def basculer_etiquette(cle: str) -> None:
    """Poser ou retirer une étiquette sur la carte ouverte."""
    carte = carte_ouverte()
    if carte is None or cle not in LIB_ETIQUETTE:
        return
    posees = list(carte["etiquettes"])
    if cle in posees:
        posees.remove(cle)
        verbe = f"a retiré l'étiquette {LIB_ETIQUETTE[cle]}"
    else:
        posees.append(cle)
        verbe = f"a posé l'étiquette {LIB_ETIQUETTE[cle]}"
    modifier(carte, f"{verbe} sur « {carte['titre']} »", etiquettes=posees)


# ── Sous-tâches et commentaires : au clic, sans « enregistrer » ───────


def ajouter_sous_tache() -> None:
    """Une sous-tâche de plus, prise du champ du tiroir."""
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    texte = str(brouillon.sous_tache).strip()[:120]
    if carte is None or not texte:
        return
    modifier(carte, f"a ajouté « {texte} » à « {carte['titre']} »",
             sous_taches=[*[dict(s) for s in carte["sous_taches"]],
                          {"texte": texte, "fait": False}])
    brouillon.sous_tache = ""


def basculer_sous_tache(rang: int) -> None:
    """Cocher ou décocher la sous-tâche numéro ``rang``."""
    carte = carte_ouverte()
    if carte is None or not 0 <= rang < len(carte["sous_taches"]):
        return
    sous = [dict(s) for s in carte["sous_taches"]]
    sous[rang]["fait"] = not sous[rang]["fait"]
    etat = "faite" if sous[rang]["fait"] else "à refaire"
    modifier(carte, f"a marqué « {sous[rang]['texte']} » {etat}",
             sous_taches=sous)


def retirer_sous_tache(rang: int) -> None:
    """Supprimer la sous-tâche numéro ``rang``."""
    carte = carte_ouverte()
    if carte is None or not 0 <= rang < len(carte["sous_taches"]):
        return
    sous = [dict(s) for i, s in enumerate(carte["sous_taches"]) if i != rang]
    modifier(carte, f"a retiré une sous-tâche de « {carte['titre']} »",
             sous_taches=sous)


def commenter() -> None:
    """Ajouter un commentaire signé de l'identité courante."""
    brouillon = Brouillon()
    carte = carte_par_id(Fiche().carte_id)
    texte = str(brouillon.commentaire).strip()[:600]
    if carte is None or not texte:
        return
    modifier(carte, f"a commenté « {carte['titre']} »",
             commentaires=[*[dict(c) for c in carte["commentaires"]],
                           {"qui": Moi().membre, "texte": texte,
                            "t": time.time()}])
    brouillon.commentaire = ""


# ── Créer, et les contrôles du bandeau ────────────────────────────────


def identifiant_libre() -> str:
    """Le prochain identifiant de carte, dérivé du plus grand existant.

    Un compteur stocké serait un second état à tenir cohérent avec la
    liste ; le dériver ne peut pas dériver.
    """
    nombres = [
        int(c["id"][1:]) for c in Tableau().cartes
        if c["id"][:1] == "c" and c["id"][1:].isdigit()
    ]
    return f"c{max(nombres, default=0) + 1:02d}"


def creer(nouvelle: Nouvelle) -> None:
    """Une carte neuve, en tête de la colonne choisie, et on l'ouvre."""
    titre = str(nouvelle.titre).strip()[:120]
    colonne = str(nouvelle.colonne)
    if not titre:
        return
    if pleine(colonne):
        ui.notification(
            f"« {LIBELLES[colonne]} » est à sa limite de "
            f"{LIMITES[colonne]} cartes.",
            variant="warning", title="Création refusée", duration_ms=4000,
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
    journaliser(ident, None, neuve, f"a créé « {titre} »")
    nouvelle.titre = ""
    ouvrir(ident)


def filtrer(filtres: Filtres) -> None:
    """Rien à faire : la valeur du contrôle est hydratée, ``deps=`` suit.

    ⚠️ **Le paramètre typé n'est pas décoratif — c'est LUI qui hydrate.**
    Écrit ``def filtrer()`` sans paramètre, le handler se déclenche, ne
    lève pas, et le serveur répond zéro octet : il n'a lu aucune valeur,
    donc aucun état n'a changé, donc aucune zone n'est à re-rendre. Les
    trois filtres étaient inertes et rien ne le disait — mesuré au probe,
    invisible à la lecture.
    """


def changer_de_membre(moi: Moi) -> None:
    """``Moi.membre`` est hydraté par le sélecteur ; rien d'autre à faire.

    Pas d'authentification ici, et c'est écrit : cet exemple met en scène
    l'état partagé, pas l'identité — ``examples/auth`` fait l'autre.
    Le validateur de :class:`Moi` ramène toute valeur inconnue, donc ce
    handler n'a rien à contrôler.
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
