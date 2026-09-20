"""kanban/donnees — the demonstration board, isolated per visitor.

``SessionState`` keeps the cards and the history in the browser's signed
session. Two visitors can therefore neither read nor modify each other's
data; the demo keeps its full behaviour inside each session.

No database: restarting the server puts the board back to its starting
state. Two other demos (``crm``, ``mad``) show SQLite; here the source of
truth fits in memory, and that is what makes the demonstration readable
in one file.

⚠️ **The seed's identifiers are WRITTEN, never drawn at random.** A
``default_factory`` on a server state is re-evaluated at every request as
long as no mutation has persisted it: a ``uuid4`` here would mint fresh
identifiers at every render, and the first drag would aim at a card that
already no longer exists.

**The order inside a column is a floating ``rang``**, not the position in
the list. Dropping between two cards takes the midpoint of their two
ranks, so a single card is rewritten — and that is what makes
``annuler`` trivial: restoring one card is enough, no neighbour has
moved. The price is written down: after thirty-odd drops at the same
spot, the floats have no midpoint left to offer. A real app renumbers
(``examples/crm`` does); a demo board has no time for that.
"""

from __future__ import annotations

import time
from typing import Any

from bretzel import Feature
from bretzel.state import SessionState, field
from examples.kanban.core.i18n import tr

#: The columns, in board order, with their **work-in-progress limit**.
#: ``None`` = no limit. The limit is a rule of the board, not a
#: decoration: it refuses a drop, and the server is what arbitrates.
#:
#: The key and the limit are language-free, so they stay constants; the
#: LABEL is not, so it lives in :func:`colonnes` — a function, because
#: :func:`~examples.kanban.core.i18n.tr` reads the request's language and
#: a module constant is evaluated once at import.
CLES: tuple[str, ...] = ("a_faire", "en_cours", "en_revue", "fini")
LIMITES: dict[str, int | None] = {
    "a_faire": None, "en_cours": 3, "en_revue": 2, "fini": None,
}


def colonnes() -> tuple[tuple[str, str, int | None], ...]:
    """``(key, label, limit)`` per column, in board order."""
    return (
        ("a_faire", tr("To do", "À faire"), None),
        ("en_cours", tr("In progress", "En cours"), 3),
        ("en_revue", tr("In review", "En revue"), 2),
        ("fini", tr("Done", "Terminé"), None),
    )


def libelles() -> dict[str, str]:
    """``key -> label`` for the columns, in the request's language."""
    return {cle: lib for cle, lib, _ in colonnes()}

#: The team. The key serves as session identity ("you are…") and as a
#: card's assignee — two roles for one table, because it is the same
#: person.
MEMBRES: tuple[tuple[str, str, str, str], ...] = (
    ("cam", "Camille Roux", "CR", "primary"),
    ("sam", "Samuel Diallo", "SD", "info"),
    ("noa", "Noa Berger", "NB", "warning"),
    ("lea", "Léa Marchand", "LM", "success"),
)

NOMS: dict[str, str] = {cle: nom for cle, nom, _, _ in MEMBRES}
INITIALES: dict[str, str] = {cle: ini for cle, _, ini, _ in MEMBRES}
COULEURS: dict[str, str] = {cle: coul for cle, _, _, coul in MEMBRES}

#: The available labels, with the semantic colour that renders them.
ETIQUETTES: tuple[tuple[str, str, str], ...] = (
    ("bug", "Bug", "error"),
    ("ux", "UX", "info"),
    ("perf", "Perf", "warning"),
    ("doc", "Doc", "muted"),
    ("infra", "Infra", "success"),
)

LIB_ETIQUETTE: dict[str, str] = {cle: lib for cle, lib, _ in ETIQUETTES}
COUL_ETIQUETTE: dict[str, str] = {cle: coul for cle, _, coul in ETIQUETTES}


def tache(
    ident: str,
    colonne: str,
    titre: str,
    qui: str,
    etiquettes: tuple[str, ...] = (),
    echeance: str = "",
    points: int = 0,
    description: str = "",
    sous_taches: tuple[tuple[str, bool], ...] = (),
    commentaires: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """A complete card, with its defaults. The ``rang`` comes after."""
    return {
        "id": ident,
        "colonne": colonne,
        "titre": titre,
        "qui": qui,
        "etiquettes": list(etiquettes),
        "echeance": echeance,
        "points": points,
        "description": description,
        "sous_taches": [{"texte": t, "fait": f} for t, f in sous_taches],
        "commentaires": [
            {"qui": q, "texte": t, "t": 0.0} for q, t in commentaires
        ],
        "rang": 0.0,
    }


#: The seed, column by column and in display order. What a real team
#: sprint produces: enough material for the board to overflow vertically,
#: which is the only way to see a column scroll.
#:
#: A FUNCTION and no longer a constant: every sentence goes through
#: :func:`~examples.kanban.core.i18n.tr`, which reads the request's
#: language. ``semer`` is called from a ``default_factory`` on a
#: ``SessionState``, hence inside a render context — the seed is
#: therefore in the language of whoever first opens the board.
def graine() -> tuple[dict[str, Any], ...]:
    """The fifteen seeded cards, in the request's language."""
    return (
        tache(
            "c01", "a_faire",
            tr("Sign-in screen: forgotten password",
               "Écran de connexion : mot de passe oublié"),
            "sam", ("ux",), "2026-09-18", 3,
            tr("The link exists but returns a 404 since the routing was "
               "reworked. To be rewired onto the new single-use token "
               "flow.",
               "Le lien existe mais renvoie une 404 depuis la refonte du "
               "routage. À rebrancher sur le nouveau flux de jetons à "
               "usage unique."),
            ((tr("Rewire the route", "Rebrancher la route"), False),
             (tr("Email template", "Gabarit de courriel"), False),
             (tr("30-minute expiry", "Expiration à 30 min"), False)),
        ),
        tache(
            "c02", "a_faire",
            tr("Audit log exportable as CSV",
               "Journal d\'audit exportable en CSV"),
            "noa", ("infra", "doc"), "2026-09-25", 5,
            tr("The large accounts ask for it for their internal audits. "
               "One row per action, the export runs as a background task.",
               "Les clients grands comptes le demandent pour leurs audits "
               "internes. Une ligne par action, l\'export tourne en tâche "
               "de fond."),
            ((tr("Paginated query", "Requête paginée"), False),
             (tr("Writing the file", "Écriture du fichier"), False),
             (tr("Button and notification", "Bouton et notification"), False),
             (tr("Document the format", "Documenter le format"), False)),
        ),
        tache(
            "c03", "a_faire",
            tr("Fix the VAT computation on credit notes",
               "Corriger le calcul de TVA sur les avoirs"),
            "lea", ("bug",), "2026-09-15", 2,
            tr("A credit note issued after a rate change applies the day\'s "
               "rate, not the original invoice\'s.",
               "Un avoir émis après un changement de taux applique le taux "
               "du jour, pas celui de la facture d\'origine."),
            ((tr("Reproduce on real data", "Reproduire sur un jeu réel"),
              True),
             (tr("Fix", "Corriger"), False)),
            (("cam", tr("Reported by two clients this week, to be "
                        "prioritised.",
                        "Signalé par deux clients cette semaine, à "
                        "prioriser.")),),
        ),
        tache(
            "c04", "a_faire",
            tr("Rework the pricing page", "Refonte de la page de tarifs"),
            "cam", ("ux",), "", 8,
            tr("Three plans instead of five, and the comparison goes below "
               "the fold. Mock-ups approved, the integration is left.",
               "Trois plans au lieu de cinq, et le comparatif passe sous le "
               "pli. Maquettes validées, reste l\'intégration."),
        ),
        tache(
            "c05", "a_faire",
            tr("Drop the moment.js dependency",
               "Retirer la dépendance à moment.js"),
            "noa", ("perf",), "", 3,
            tr("68 kB to format three dates. Native formatting is enough "
               "now that the old browsers are no longer supported.",
               "68 Ko pour formater trois dates. Le formatage natif suffit "
               "depuis qu\'on ne supporte plus les vieux navigateurs."),
        ),
        tache(
            "c06", "a_faire",
            tr("A ten-minute getting-started guide",
               "Guide de démarrage en dix minutes"),
            "sam", ("doc",), "2026-10-02", 5,
            tr("The sign-up drop-off rate is decided in the first five "
               "minutes. A written walkthrough, tested on three people.",
               "Le taux d\'abandon à l\'inscription se joue dans les cinq "
               "premières minutes. Un parcours écrit, testé sur trois "
               "personnes."),
        ),
        tache(
            "c07", "en_cours",
            tr("Merge duplicate accounts", "Fusion des comptes en double"),
            "lea", ("bug", "infra"), "2026-09-12", 8,
            tr("Two accounts created with the same address in upper and in "
               "lower case. They must be merged without losing the "
               "history.",
               "Deux comptes créés avec la même adresse en majuscules et en "
               "minuscules. Il faut fusionner sans perdre l\'historique."),
            ((tr("Duplicate detection", "Détection des doublons"), True),
             (tr("Merge screen", "Écran de fusion"), True),
             (tr("Replaying the history", "Rejeu de l\'historique"), False)),
            (("noa", tr("The detection runs, 412 pairs found in the "
                        "database.",
                        "La détection tourne, 412 paires trouvées en "
                        "base.")),
             ("lea", tr("I am taking the merge screen, ready tomorrow.",
                        "Je prends l\'écran de fusion, dispo demain."))),
        ),
        tache(
            "c08", "en_cours",
            tr("Dashboard caching", "Cache des tableaux de bord"),
            "noa", ("perf",), "2026-09-16", 5,
            tr("The dashboard recomputes twelve aggregates at every load. A "
               "five-minute cache is enough, invalidated on write.",
               "Le tableau de bord recalcule douze agrégats à chaque "
               "chargement. Un cache de cinq minutes suffit, invalidé à "
               "l\'écriture."),
            ((tr("Choosing the cache key", "Choisir la clé de cache"), True),
             (tr("Invalidation", "Invalidation"), False)),
        ),
        tache(
            "c09", "en_cours",
            tr("Date picker accessibility",
               "Accessibilité du sélecteur de dates"),
            "cam", ("ux", "bug"), "2026-09-19", 3,
            tr("The calendar cannot be reached from the keyboard, and the "
               "screen reader announces \"button\" without saying which "
               "date.",
               "Impossible d\'atteindre le calendrier au clavier, et le "
               "lecteur d\'écran annonce « bouton » sans dire quelle date."),
            ((tr("Tab order", "Ordre de tabulation"), True),
             (tr("ARIA labels", "Étiquettes ARIA"), False),
             (tr("Screen-reader test", "Test au lecteur d\'écran"), False)),
        ),
        tache(
            "c10", "en_revue",
            tr("Rate limiting on the public API",
               "Limitation de débit sur l\'API publique"),
            "sam", ("infra",), "2026-09-11", 5,
            tr("A hundred requests per minute per token, with the standard "
               "headers so the clients know where they stand.",
               "Cent requêtes par minute et par jeton, avec les en-têtes "
               "standard pour que les clients sachent où ils en sont."),
            ((tr("In-memory counter", "Compteur en mémoire"), True),
             (tr("Quota headers", "En-têtes de quota"), True),
             (tr("Documentation", "Documentation"), True)),
            (("cam", tr("Reviewed, only the expired-token case is missing.",
                        "Relu, il manque juste le cas du jeton expiré.")),),
        ),
        tache(
            "c11", "en_revue",
            tr("Spanish translation of the interface",
               "Traduction espagnole de l\'interface"),
            "lea", ("doc", "ux"), "", 8,
            tr("1 240 strings reviewed by a native translator. The "
               "overflows on long labels are left to check.",
               "1 240 chaînes relues par une traductrice native. Reste à "
               "vérifier les débordements sur les libellés longs."),
            ((tr("Extracting the strings", "Extraction des chaînes"), True),
             (tr("Review", "Relecture"), True),
             (tr("Check the overflows", "Vérifier les débordements"), False)),
        ),
        tache(
            "c12", "fini",
            tr("Migration to the new billing engine",
               "Migration vers le nouveau moteur de facturation"),
            "noa", ("infra",), "", 13,
            tr("Switched over on a Sunday morning, no visible outage. The "
               "old engine stays readable read-only until December.",
               "Bascule faite un dimanche matin, aucune interruption "
               "visible. L\'ancien moteur reste lisible en lecture seule "
               "jusqu\'en décembre."),
            ((tr("Dual writing", "Double écriture"), True),
             (tr("Switch over", "Bascule"), True),
             (tr("Clean-up", "Nettoyage"), True)),
        ),
        tache(
            "c13", "fini",
            tr("Sign in with Google and Microsoft",
               "Connexion par Google et Microsoft"),
            "cam", ("infra", "ux"), "", 8,
            tr("Both providers wired, the existing account is attached by "
               "the verified address.",
               "Les deux fournisseurs branchés, le compte existant est "
               "rattaché par l\'adresse vérifiée."),
            ((tr("Google", "Google"), True),
             (tr("Microsoft", "Microsoft"), True),
             (tr("Attaching", "Rattachement"), True)),
        ),
        tache(
            "c14", "fini",
            tr("Fix the PDF export truncated beyond 40 pages",
               "Corriger l\'export PDF tronqué au-delà de 40 pages"),
            "sam", ("bug",), "", 3,
            tr("The generator cut off at the fortieth page without a word. "
               "The buffer was flushed too early.",
               "Le générateur coupait à la quarantième page sans rien dire. "
               "Le tampon était vidé trop tôt."),
            ((tr("Reproduce", "Reproduire"), True),
             (tr("Fix", "Corriger"), True),
             (tr("Regression test", "Test de non-régression"), True)),
        ),
        tache(
            "c15", "fini",
            tr("Cookie consent banner",
               "Bandeau de consentement aux cookies"),
            "lea", ("doc",), "", 2,
            tr("Refused by default, no tracker before the click. Approved "
               "by the firm.",
               "Refus par défaut, aucun traceur avant le clic. Validé par "
               "le cabinet."),
        ),
    )


def copie(carte: dict[str, Any]) -> dict[str, Any]:
    """A card detached from the original, nested lists included.

    ⚠️ ``{**carte}`` is NOT enough: the three lists would stay shared, so
    the journal's "before" snapshot would change at the same time as the
    card it is supposed to keep — and undoing would give nothing back.
    """
    return {
        **carte,
        "etiquettes": list(carte["etiquettes"]),
        "sous_taches": [dict(s) for s in carte["sous_taches"]],
        "commentaires": [dict(c) for c in carte["commentaires"]],
    }


def semer() -> list[dict[str, Any]]:
    """The seed, with a rank assigned BY POSITION in its column.

    The ranks start at 1, 2, 3… so there is always a free midpoint
    between two neighbours for the first drops.
    """
    compteurs: dict[str, float] = dict.fromkeys(CLES, 0.0)
    cartes: list[dict[str, Any]] = []
    for modele in graine():
        carte = copie(modele)
        compteurs[carte["colonne"]] += 1.0
        carte["rang"] = compteurs[carte["colonne"]]
        cartes.append(carte)
    return cartes


class Tableau(SessionState):
    """The board: its cards, and the story of what happened to them.

    ``journal`` + ``curseur`` form a classic undo stack: the cursor
    counts the APPLIED entries, undo moves it back, redo forward, and a
    new action truncates everything that followed. Each entry carries the
    card BEFORE and AFTER — restoring a dictionary is enough, there is no
    movement to replay backwards.

    The history belongs to the session that created the card: undo and
    redo never act on another visitor's work.
    """

    cartes: list[dict[str, Any]] = field(default_factory=semer)
    journal: list[dict[str, Any]] = field(default_factory=list)
    curseur: int = field(default=0)


def carte_par_id(ident: str) -> dict[str, Any] | None:
    """The card carrying this identifier, or ``None``."""
    for carte in Tableau().cartes:
        if carte["id"] == ident:
            return carte
    return None


def correspond(carte: dict[str, Any], qui: str, etiquette: str,
               texte: str) -> bool:
    """Does this card survive the banner's three filters?"""
    if qui != "tous" and carte["qui"] != qui:
        return False
    if etiquette != "toutes" and etiquette not in carte["etiquettes"]:
        return False
    if texte:
        cible = (carte["titre"] + " " + carte["description"]).casefold()
        if texte.casefold() not in cible:
            return False
    return True


def colonne_de(cle: str, qui: str = "tous", etiquette: str = "toutes",
               texte: str = "") -> list[dict[str, Any]]:
    """A column's VISIBLE cards, in rank order.

    The filters are applied here, so the same function serves the
    rendering and the computation of a drop's neighbours. Letting them
    diverge would amount to inserting a card between two neighbours the
    reader could not see.
    """
    return sorted(
        (c for c in Tableau().cartes
         if c["colonne"] == cle and correspond(c, qui, etiquette, texte)),
        key=lambda c: c["rang"],
    )


def occupation(cle: str) -> int:
    """How many cards are IN the column — filters excluded.

    A work-in-progress limit counts real work, not what a filter lets you
    see. Hiding somebody else's cards does not free a slot.
    """
    return sum(1 for c in Tableau().cartes if c["colonne"] == cle)


def pleine(cle: str) -> bool:
    """Does the column refuse one more card?"""
    limite = LIMITES.get(cle)
    return limite is not None and occupation(cle) >= limite


def avancement(carte: dict[str, Any]) -> tuple[int, int]:
    """Subtasks done, subtasks in total."""
    sous = carte["sous_taches"]
    return sum(1 for s in sous if s["fait"]), len(sous)


def entre(avant: float | None, apres: float | None) -> float:
    """A free rank between two neighbours, either of which may be absent."""
    if avant is None and apres is None:
        return 1.0
    if avant is None:
        return float(apres) - 1.0  # type: ignore[arg-type]
    if apres is None:
        return float(avant) + 1.0
    return (float(avant) + float(apres)) / 2.0


def depuis(instant: float) -> str:
    """"12 s ago" — derived at display time, never stored.

    A date written into the state would be wrong the second after, and it
    is exactly the kind of field one forgets to update when a new write
    arrives.
    """
    if not instant:
        return ""
    ecart = max(0, int(time.time() - instant))
    if ecart < 60:
        return tr(f"{ecart} s ago", f"il y a {ecart} s")
    if ecart < 3600:
        return tr(f"{ecart // 60} min ago", f"il y a {ecart // 60} min")
    if ecart < 86400:
        return tr(f"{ecart // 3600} h ago", f"il y a {ecart // 3600} h")
    return tr(f"{ecart // 86400} d ago", f"il y a {ecart // 86400} j")


def echeance_lisible(valeur: str) -> str:
    """``2026-09-18`` → ``18/09``. Empty stays empty."""
    if not valeur or len(valeur) < 10:
        return ""
    return f"{valeur[8:10]}/{valeur[5:7]}"


feature = Feature(
    name="donnees", kind="data",
    provides=[Tableau, colonnes, libelles, MEMBRES, ETIQUETTES, semer,
              copie,
              carte_par_id, colonne_de, occupation, pleine, correspond,
              avancement, entre, depuis, echeance_lisible],
)
