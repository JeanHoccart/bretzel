"""features/import_data — data : l'import en deux temps, et les archives.

``kind="data"``. EF-J1 à EF-J8 et EF-N1 à EF-N3.

EF-J1 — **on analyse, PUIS on valide**
----------------------------------------
*« Rien n'entre en base avant que le professeur ait vu la liste — un
import est la seule opération qui crée trois cents élèves d'un coup. »*
D'où deux fonctions et pas une : :func:`analyser` ne touche à rien,
:func:`valider` écrit.

EF-J5 — **l'appariement se fait par NOM, jamais par position**
----------------------------------------------------------------
**Piège n° 5**, et c'est le plus visible de tous : *« un élève parti
pendant l'été suffirait à décaler tout le reste, et à poser chaque visage
sur son voisin »*. La comparaison porte sur le nom ET le prénom
ensemble, sans accents ni casse (EF-J6) — « courty leane » doit retrouver
« COURTY Léane » — et les deux champs restent DISTINCTS (EF-C7).

EF-J3 — une classe qui a DÉJÀ des élèves est refusée
------------------------------------------------------
*« Un second passage y dupliquerait la liste entière. »* Une classe créée
vide par l'emploi du temps (EF-B6) est en revanche retrouvée par son code
et remplie : c'est exactement le cas normal de la rentrée.
"""

from __future__ import annotations

import unicodedata
from datetime import date

from bretzel import Feature
from bretzel.state import AppState, field
from examples.ecole.core.db import execute, query, scalar
from examples.ecole.core.domain import cycle_propose, niveau_du_code
from examples.ecole.features.annees import garde_ecriture


class ImportRev(AppState):
    """Le jeton des zones d'import. Même raison que les autres."""

    rev: int = field(default=0, merge="add")


def sans_accents(texte: str) -> str:
    """La forme comparable d'un nom (EF-J6).

    *« La comparaison porte sur le nom ET le prénom ensemble, sans
    accents ni casse : "courty leane" doit retrouver "COURTY Léane". »*
    Les deux champs restent distincts — c'est l'appelant qui les
    rapproche, pas cette fonction qui les fond.
    """
    plie = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in plie if not unicodedata.combining(c)).lower()


def cle_de(nom: str, prenom: str) -> str:
    """La clé d'appariement : nom ET prénom, jamais l'un des deux."""
    return f"{sans_accents(nom.strip())}|{sans_accents(prenom.strip())}"


def lire_csv(texte: str) -> list[dict]:
    """Le dépôt d'EF-K (hors périmètre : les `.xls` BIFF8, § 3.2).

    Une ligne par élève, ``NOM;Prénom`` ou ``NOM,Prénom``. Le format est
    volontairement pauvre : *« lire les .xls de l'établissement mesure la
    bibliothèque, pas le framework »*, donc le cahier le remplace par un
    dépôt CSV.

    ⚠️ Ce qui n'est PAS reconnu est rendu tel quel (EF-J7) : *« un nom
    absent de la classe, deux homonymes, un élève sans photo sont rendus
    tels quels, à l'écran, pour que le professeur décide »*. Une ligne
    illisible devient donc une ligne en erreur, pas une ligne sautée.
    """
    lignes: list[dict] = []
    for numero, brute in enumerate(texte.splitlines(), start=1):
        ligne = brute.strip()
        if not ligne or ligne.lower().startswith(("nom;", "nom,")):
            continue
        morceaux = [m.strip() for m in ligne.replace(",", ";").split(";")]
        morceaux = [m for m in morceaux if m]
        if len(morceaux) < 2:
            lignes.append({"ligne": numero, "brut": ligne, "nom": "",
                           "prenom": "", "erreur": "nom et prénom attendus"})
            continue
        lignes.append({"ligne": numero, "brut": ligne, "nom": morceaux[0],
                       "prenom": morceaux[1], "erreur": ""})
    return lignes


def analyser(annee_id: int, code: str, texte: str) -> dict:
    """EF-J1 — **le premier temps : on regarde, on n'écrit rien.**

    Rend ``{classe, refus, lignes, doublons, connus, inconnus}``. Aucune
    écriture, aucune exception : l'écran doit pouvoir tout montrer, y
    compris ce qui cloche.
    """
    code = code.strip()
    classes = query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    classe = classes[0] if classes else None

    refus = ""
    if not code:
        refus = "Il faut un code de classe."
    elif classe is not None:
        effectif = scalar(
            "SELECT COUNT(*) FROM inscriptions WHERE classe_id = ? "
            "AND fin IS NULL", (classe["id"],)) or 0
        if effectif:
            # EF-J3 : *« un second passage y dupliquerait la liste
            # entière »*.
            refus = (f"{code} a déjà {effectif} élèves. Un second import y "
                     f"dupliquerait la liste entière. Pour remplacer les "
                     f"photos, c'est le bouton séparé.")

    lignes = lire_csv(texte)
    vues: dict[str, int] = {}
    for ligne in lignes:
        if ligne["erreur"]:
            continue
        cle = cle_de(ligne["nom"], ligne["prenom"])
        vues[cle] = vues.get(cle, 0) + 1
    for ligne in lignes:
        if not ligne["erreur"] and vues[cle_de(ligne["nom"],
                                               ligne["prenom"])] > 1:
            # EF-J7 : deux homonymes sont DITS, pas départagés au hasard.
            ligne["erreur"] = "en double dans le fichier"

    deja = deja_en_base(annee_id) if classe is None else {}
    for ligne in lignes:
        cle = cle_de(ligne["nom"], ligne["prenom"])
        ligne["connu"] = deja.get(cle, "")

    return {
        "classe": classe,
        "code": code,
        "refus": refus,
        "lignes": lignes,
        "valides": [li for li in lignes if not li["erreur"]],
        "erreurs": [li for li in lignes if li["erreur"]],
    }


def deja_en_base(annee_id: int) -> dict[str, str]:
    """``clé → code de classe`` pour les élèves déjà inscrits cette année.

    Sert à DIRE qu'un nom du fichier est déjà ailleurs (EF-J7), pas à
    l'écarter : c'est le professeur qui décide.
    """
    return {
        cle_de(r["nom"], r["prenom"]): r["code"]
        for r in query(
            """
            SELECT e.nom, e.prenom, c.code
            FROM inscriptions i JOIN eleves e ON e.id = i.eleve_id
            JOIN classes c ON c.id = i.classe_id
            WHERE c.annee_id = ? AND i.fin IS NULL
            """,
            (annee_id,))
    }


def valider(annee_id: int, code: str, lignes: list[dict]) -> int:
    """EF-J1 — **le second temps : maintenant on écrit.**

    Une classe absente est CRÉÉE (le cas de la rentrée) ; une classe
    créée vide par l'emploi du temps est retrouvée par son code et
    remplie (EF-J3). Rend le nombre d'élèves ajoutés.
    """
    garde_ecriture(annee_id)
    classes = query(
        "SELECT id FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    if classes:
        classe_id = classes[0]["id"]
    else:
        niveau = niveau_du_code(code)
        classe_id = execute(
            "INSERT INTO classes (annee_id, code, libelle, cycle, niveau, "
            "rang) VALUES (?, ?, ?, ?, ?, 0)",
            (annee_id, code, code, cycle_propose(niveau), niveau))

    debut = query("SELECT debut FROM annees WHERE id = ?",
                  (annee_id,))[0]["debut"]
    ajoutes = 0
    for ligne in lignes:
        if ligne.get("erreur"):
            continue
        eleve_id = execute(
            "INSERT INTO eleves (nom, prenom) VALUES (?, ?)",
            (ligne["nom"][:60], ligne["prenom"][:60]))
        execute(
            "INSERT INTO inscriptions (eleve_id, classe_id, debut, fin) "
            "VALUES (?, ?, ?, NULL)", (eleve_id, classe_id, debut))
        ajoutes += 1
    ImportRev().rev += 1
    return ajoutes


def apparier_photos(annee_id: int, classe_id: int,
                    lignes: list[dict]) -> dict:
    """EF-J4, EF-J5 — **remplacer les photos, sans toucher à la classe.**

    *« "Remplacer les photos" est un bouton SÉPARÉ de "Ajouter les
    élèves". On ne veut surtout pas créer trente doublons en croyant
    rafraîchir des photos. »* Cette fonction ne crée donc AUCUN élève et
    n'en retire aucun : elle apparie par NOM et pose les images.

    Rend ``{poses, absents}`` — et les absents sont DITS (EF-J7).
    """
    garde_ecriture(annee_id)
    en_classe = {
        cle_de(r["nom"], r["prenom"]): r["id"]
        for r in query(
            """
            SELECT e.id, e.nom, e.prenom FROM inscriptions i
            JOIN eleves e ON e.id = i.eleve_id
            WHERE i.classe_id = ? AND i.fin IS NULL
            """,
            (classe_id,))
    }
    poses, absents = 0, []
    for ligne in lignes:
        if ligne.get("erreur"):
            continue
        eleve_id = en_classe.get(cle_de(ligne["nom"], ligne["prenom"]))
        if eleve_id is None:
            absents.append(f"{ligne['nom']} {ligne['prenom']}")
            continue
        # EF-J8 : le cadrage est une TRANSFORMATION, pas un remplacement —
        # l'image d'origine est conservée. Ici le jeu de démonstration ne
        # porte que des initiales (§ 12), donc on note l'ÉTAT du cadrage
        # plutôt qu'un fichier : c'est lui que l'écran distingue.
        execute("UPDATE eleves SET photo = ? WHERE id = ?",
                ("cadrage-par-defaut", eleve_id))
        poses += 1
    ImportRev().rev += 1
    return {"poses": poses, "absents": absents}


# ── Les archives (EF-N) ──────────────────────────────────────────────

def archive_de(classe_id: int) -> dict:
    """EF-N1 — *« tout y est, dans l'ordre où on le cherche »*.

    Trombinoscope, notes des TROIS trimestres, appréciations, bilan. Une
    seule lecture, parce que l'archive se fabrique d'un coup (EF-N3) et
    qu'une page par trimestre obligerait à trois passages.
    """
    classes = query(
        "SELECT c.id, c.code, c.libelle, c.cycle, c.prof_principal, "
        "a.libelle AS annee FROM classes c JOIN annees a ON a.id = c.annee_id "
        "WHERE c.id = ?", (classe_id,))
    if not classes:
        return {}
    eleves = query(
        """
        SELECT e.id, e.nom, e.prenom FROM inscriptions i
        JOIN eleves e ON e.id = i.eleve_id
        WHERE i.classe_id = ?
        ORDER BY e.nom COLLATE NOCASE, e.prenom COLLATE NOCASE
        """,
        (classe_id,),
    )
    notes = query(
        """
        SELECT n.eleve_id, ev.trimestre, ev.nom, ev.bareme, ev.coefficient,
               n.absent, n.valeur
        FROM notes n JOIN evaluations ev ON ev.id = n.evaluation_id
        WHERE ev.classe_id = ? ORDER BY ev.trimestre, ev.date
        """,
        (classe_id,),
    )
    appreciations = query(
        "SELECT eleve_id, trimestre, appreciation FROM fiches "
        "WHERE classe_id = ? AND appreciation <> ''", (classe_id,))
    return {"classe": classes[0], "eleves": eleves, "notes": notes,
            "appreciations": appreciations}


def classes_archivables(annee_id: int) -> list[dict]:
    return query(
        "SELECT id, code, libelle FROM classes WHERE annee_id = ? "
        "ORDER BY rang, code", (annee_id,))


def photo_datee() -> str:
    """La date d'aujourd'hui, pour l'en-tête d'une archive (EF-N2).

    *« C'est une ARCHIVE, pas un bulletin : elle doit se relire dans dix
    ans sans le programme qui l'a produite. »* Une archive sans sa date
    de fabrication ne se situe pas.
    """
    return date.today().isoformat()


feature = Feature(
    name="import_data",
    kind="data",
    provides=[
        ImportRev, sans_accents, cle_de, lire_csv, analyser, deja_en_base,
        valider, apparier_photos, archive_de, classes_archivables,
        photo_datee,
    ],
    uses=["db", "annees"],
)
