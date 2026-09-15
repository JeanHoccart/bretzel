"""features/grille_data — data : la grille type, ses exceptions, son retour.

``kind="data"``. Elle répond à **une** question composée : *que voit-on
la semaine du tant ?* — et la réponse mélange trois sources que le cahier
ordonne explicitement (EF-K5) :

1. la **grille type**, qui se répète par jour × horaire × semaine A/B ;
2. les **heures exceptionnelles**, posées sur de VRAIES dates, et qui
   l'emportent : une heure en plus, ou une annulation ;
3. les **périodes sans classe**, qui vident un jour entier (EF-B4).

*« Le cahier lit le résultat de la grille ET des exceptions, jamais la
grille seule — sinon il proposerait de noter une classe qu'on n'a pas
eue »* : c'est pour ça que :func:`semaine_affichee` est la seule porte,
et que le lot 9 la réutilisera telle quelle.

Le retour en arrière (EF-B12)
------------------------------
La grille entière est mise de côté **avant chaque modification**, en
JSON, et les vingt dernières sont gardées. Restaurer réécrit les
créneaux — sauf ceux dont la classe a disparu entre-temps : *« une classe
supprimée ne ressuscite pas : sa case est perdue, le reste revient »*.
C'est la seule forme qui ne recrée pas de donnée à partir d'une photo.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from bretzel import Feature
from examples.ecole.core.db import execute, query
from examples.ecole.core.domain import (
    blocs_du_jour,
    cycle_propose,
    lire_saisie,
    niveau_du_code,
    periode_sans_classe,
    rang_du_niveau,
    semaine_ab,
)
from examples.ecole.features.annees import garde_ecriture

#: Combien de grilles précédentes on garde (§ 5.4). Vingt, c'est une
#: session de reprise d'emploi du temps entière — au-delà, on ne revient
#: plus « en arrière », on restaure une vieille version, et ce n'est pas
#: le même geste.
GRILLES_GARDEES = 20


def codes_de_lannee(annee_id: int) -> frozenset[str]:
    """Les codes de classe existants — l'entrée d'EF-B8.

    C'est cette liste qui décide si « 2nde - 4 » se découpe ou reste
    entier. Elle est relue à chaque saisie : une classe créée à la case
    d'avant doit être reconnue à la suivante.
    """
    return frozenset(
        r["code"] for r in query(
            "SELECT code FROM classes WHERE annee_id = ?", (annee_id,))
    )


def lundi_affiche(annee: dict, demande: str) -> date:
    """Le lundi de la semaine à montrer — demandée, ou celle d'aujourd'hui.

    Une demande hors de l'année est ramenée dans l'année : un lien
    partagé d'une année sur l'autre ouvre alors la première semaine
    plutôt qu'une grille vide sans explication.
    """
    debut = date.fromisoformat(annee["debut"])
    fin = date.fromisoformat(annee["fin"])
    if demande:
        try:
            voulu = date.fromisoformat(demande)
        except ValueError:
            voulu = date.today()
    else:
        voulu = date.today()
    voulu = min(max(voulu, debut), fin)
    return voulu - timedelta(days=voulu.weekday())


def semaine_affichee(annee: dict, lundi: date) -> dict:
    """Tout ce que la grille d'une semaine doit savoir, en une lecture.

    Rend ``{"lettre", "jours": [{date, periode, blocs}], "bornes"}``.

    ⚠️ **``lettre`` peut être ``None``**, et l'écran doit le DIRE plutôt
    que d'afficher « A » (RT-4). Sans date de référence, la grille type
    n'est pas lisible du tout : on ne sait pas quelle semaine on regarde.
    """
    lundi_ref = (date.fromisoformat(annee["lundi_ref"])
                 if annee["lundi_ref"] else None)
    lettre = semaine_ab(lundi, lundi_ref)

    bornes = {
        r["rang"]: (r["debut"], r["fin"])
        for r in query(
            "SELECT rang, debut, fin FROM horaires WHERE annee_id = ? "
            "ORDER BY rang", (annee["id"],))
    }
    periodes = [
        (r["libelle"], date.fromisoformat(r["debut"]),
         date.fromisoformat(r["fin"]))
        for r in query("SELECT libelle, debut, fin FROM vacances "
                       "WHERE annee_id = ?", (annee["id"],))
    ]

    # La grille type de la semaine affichée. Sans lettre, il n'y a rien à
    # lire : on rend les jours vides plutôt que d'inventer une moitié.
    typiques: dict[tuple[int, int], dict] = {}
    if lettre:
        for ligne in query(
            "SELECT cr.jour, h.rang, c.code, cr.nature, cr.salle "
            "FROM creneaux cr "
            "JOIN horaires h ON h.id = cr.horaire_id "
            "JOIN classes c ON c.id = cr.classe_id "
            "WHERE cr.annee_id = ? AND cr.semaine = ?",
            (annee["id"], lettre),
        ):
            typiques[(ligne["jour"], ligne["rang"])] = {
                "code": ligne["code"], "nature": ligne["nature"],
                "salle": ligne["salle"], "exception": False,
            }

    # Les exceptions de CES dates-là. Elles l'emportent : une classe pose
    # une heure en plus, une ligne sans classe l'annule (EF-B11).
    samedi = lundi + timedelta(days=5)
    exceptions: dict[tuple[str, int], dict | None] = {}
    for ligne in query(
        "SELECT e.jour, h.rang, c.code, e.salle FROM heures_exceptionnelles e "
        "JOIN horaires h ON h.id = e.horaire_id "
        "LEFT JOIN classes c ON c.id = e.classe_id "
        "WHERE e.annee_id = ? AND e.jour BETWEEN ? AND ?",
        (annee["id"], lundi.isoformat(), samedi.isoformat()),
    ):
        exceptions[(ligne["jour"], ligne["rang"])] = (
            {"code": ligne["code"], "nature": "", "salle": ligne["salle"],
             "exception": True}
            if ligne["code"] else None
        )

    # Ce qui est déjà consigné au cahier de texte, pour la pastille
    # d'EF-B13. La liste ne porte QUE sur la semaine affichée — la tenir
    # pour l'année entière coûterait cent cinquante lignes pour six.
    consignees = {
        (r["date"], r["code"])
        for r in query(
            "SELECT ca.date, c.code FROM cahier ca "
            "JOIN classes c ON c.id = ca.classe_id "
            "WHERE ca.date BETWEEN ? AND ? AND c.annee_id = ?",
            (lundi.isoformat(), samedi.isoformat(), annee["id"]),
        )
    }

    jours = []
    for index in range(6):
        jour = lundi + timedelta(days=index)
        iso = jour.isoformat()
        cases: dict[int, dict] = {}
        for rang in bornes:
            case = exceptions.get((iso, rang), _MANQUE)
            if case is _MANQUE:
                case = typiques.get((index, rang))
            if case is not None:
                cases[rang] = dict(case)
        blocs = blocs_du_jour(cases, bornes)
        for bloc in blocs:
            bloc["consignee"] = (iso, bloc["code"]) in consignees
            # ⚠️ Le drapeau d'EXCEPTION se recolle ICI, après la fusion,
            # et il a manqué une heure : ``blocs_du_jour`` construit un
            # dict NEUF (debut / fin / code / nature / salles) et n'a
            # aucune raison de connaître les exceptions — c'est une règle
            # de calendrier, pas de mise en bloc. Sans ce recollage,
            # ``bloc["exception"]`` était toujours absent et une heure
            # posée à la main rendait exactement comme un cours ordinaire.
            # Trouvé par le probe, pas en relisant : les deux formes
            # produisent un HTML valide.
            bloc["exception"] = any(
                cases[rang].get("exception")
                for rang in range(bloc["debut"], bloc["fin"] + 1)
                if rang in cases
            )
        jours.append({
            "date": jour,
            "periode": periode_sans_classe(jour, periodes),
            "cases": cases,
            "blocs": blocs,
        })

    return {"lettre": lettre, "jours": jours, "bornes": bornes}


#: Sentinelle : une exception qui ANNULE est un ``None`` légitime, donc
#: ``None`` ne peut pas vouloir dire « pas d'exception ici ».
_MANQUE = object()


# ── Les écritures ────────────────────────────────────────────────────

def creer_classe_vide(annee_id: int, code: str) -> int:
    """EF-B6 — *« un code inconnu crée la classe, vide »*.

    *L'emploi du temps arrive fin août, les listes d'élèves à la
    rentrée* : refuser un code inconnu obligerait à créer dix classes à
    la main avant de pouvoir saisir la première heure.

    Le cycle et le niveau sont PROPOSÉS depuis le code (RT-3), une fois,
    ici — et corrigeables ensuite dans l'écran de la classe.
    """
    garde_ecriture(annee_id)
    niveau = niveau_du_code(code)
    rang = rang_du_niveau(niveau) * 10
    return execute(
        "INSERT INTO classes (annee_id, code, libelle, cycle, niveau, rang) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (annee_id, code, code, cycle_propose(niveau), niveau, rang),
    )


def sauver_grille(annee_id: int) -> None:
    """Met la grille entière de côté, AVANT une modification (EF-B12).

    La photo porte les CODES de classe, pas leurs identifiants : c'est ce
    qui permet à la restauration de sauter proprement une classe
    supprimée entre-temps, au lieu de buter sur une clé étrangère morte.
    """
    photo = query(
        "SELECT cr.jour, h.rang, cr.semaine, c.code, cr.nature, cr.salle "
        "FROM creneaux cr "
        "JOIN horaires h ON h.id = cr.horaire_id "
        "JOIN classes c ON c.id = cr.classe_id "
        "WHERE cr.annee_id = ?",
        (annee_id,),
    )
    execute(
        "INSERT INTO grilles_precedentes (annee_id, pose_le, contenu) "
        "VALUES (?, ?, ?)",
        (annee_id, date.today().isoformat(), json.dumps(photo)),
    )
    execute(
        "DELETE FROM grilles_precedentes WHERE annee_id = ? AND id NOT IN "
        "(SELECT id FROM grilles_precedentes WHERE annee_id = ? "
        " ORDER BY id DESC LIMIT ?)",
        (annee_id, annee_id, GRILLES_GARDEES),
    )


def poser_case(annee_id: int, jour: int, rang: int, semaine: str,
               saisie: str) -> str:
    """Pose (ou vide) une case de la grille TYPE. Rend le code retenu.

    La saisie entière passe par
    :func:`~examples.ecole.core.domain.lire_saisie` — le découpage en
    classe / nature / salle est une règle de domaine, pas un détail
    d'écran, et c'est le piège n° 1.
    """
    garde_ecriture(annee_id)
    sauver_grille(annee_id)
    code, nature, salle = lire_saisie(saisie, codes_de_lannee(annee_id))
    if not code:
        execute(
            "DELETE FROM creneaux WHERE annee_id = ? AND jour = ? "
            "AND semaine = ? AND horaire_id = "
            "(SELECT id FROM horaires WHERE annee_id = ? AND rang = ?)",
            (annee_id, jour, semaine, annee_id, rang),
        )
        return ""

    classe_id = classe_id_de(annee_id, code)
    if classe_id is None:
        classe_id = creer_classe_vide(annee_id, code)
    execute(
        "INSERT INTO creneaux "
        "(annee_id, jour, horaire_id, semaine, classe_id, nature, salle) "
        "VALUES (?, ?, "
        " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), "
        " ?, ?, ?, ?) "
        "ON CONFLICT (annee_id, jour, horaire_id, semaine) DO UPDATE SET "
        "classe_id = excluded.classe_id, nature = excluded.nature, "
        "salle = excluded.salle",
        (annee_id, jour, annee_id, rang, semaine, classe_id, nature, salle),
    )
    return code


def annuler_derniere_grille(annee_id: int) -> bool:
    """Rend la grille telle qu'elle était (EF-B12). Faux s'il n'y a rien.

    *« Une classe supprimée entre-temps ne ressuscite pas : sa case est
    perdue, le reste revient. »* La photo est donc relue code par code,
    et les codes inconnus sont SAUTÉS — pas recréés. Recréer une classe
    supprimée exprès serait pire que de perdre sa case.
    """
    garde_ecriture(annee_id)
    lignes = query(
        "SELECT id, contenu FROM grilles_precedentes WHERE annee_id = ? "
        "ORDER BY id DESC LIMIT 1", (annee_id,))
    if not lignes:
        return False

    photo = json.loads(lignes[0]["contenu"])
    execute("DELETE FROM creneaux WHERE annee_id = ?", (annee_id,))
    vivantes = codes_de_lannee(annee_id)
    for case in photo:
        if case["code"] not in vivantes:
            continue
        execute(
            "INSERT INTO creneaux "
            "(annee_id, jour, horaire_id, semaine, classe_id, nature, salle) "
            "VALUES (?, ?, "
            " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), "
            " ?, ?, ?, ?)",
            (annee_id, case["jour"], annee_id, case["rang"], case["semaine"],
             classe_id_de(annee_id, case["code"]), case["nature"],
             case["salle"]),
        )
    execute("DELETE FROM grilles_precedentes WHERE id = ?", (lignes[0]["id"],))
    return True


def poser_exception(annee_id: int, jour: str, rang: int, code: str) -> None:
    """Une heure en plus, ou une ANNULATION (EF-B11).

    ``code`` vide = annulation. *« Une case du calendrier ne porte qu'une
    décision : reposer la même case remplace »* — c'est l'unicité
    ``(annee, jour, horaire)`` du schéma qui le tient, pas un test ici.
    """
    garde_ecriture(annee_id)
    classe_id = classe_id_de(annee_id, code) if code else None
    execute(
        "INSERT INTO heures_exceptionnelles "
        "(annee_id, jour, horaire_id, classe_id, salle) VALUES (?, ?, "
        " (SELECT id FROM horaires WHERE annee_id = ? AND rang = ?), ?, '') "
        "ON CONFLICT (annee_id, jour, horaire_id) DO UPDATE SET "
        "classe_id = excluded.classe_id",
        (annee_id, jour, annee_id, rang, classe_id),
    )


def retirer_exception(annee_id: int, jour: str, rang: int) -> None:
    """Retire la décision d'une case : la grille type reprend la main."""
    garde_ecriture(annee_id)
    execute(
        "DELETE FROM heures_exceptionnelles WHERE annee_id = ? AND jour = ? "
        "AND horaire_id = "
        "(SELECT id FROM horaires WHERE annee_id = ? AND rang = ?)",
        (annee_id, jour, annee_id, rang),
    )


def regler_horaire(annee_id: int, rang: int, debut: str, fin: str) -> None:
    """Règle les bornes d'un créneau POUR TOUTE L'ANNÉE (EF-B3)."""
    garde_ecriture(annee_id)
    execute(
        "UPDATE horaires SET debut = ?, fin = ? WHERE annee_id = ? AND rang = ?",
        (debut, fin, annee_id, rang),
    )


def classe_id_de(annee_id: int, code: str) -> int | None:
    """L'identifiant d'une classe par son code, ou ``None``."""
    lignes = query(
        "SELECT id FROM classes WHERE annee_id = ? AND code = ?",
        (annee_id, code))
    return lignes[0]["id"] if lignes else None


feature = Feature(
    name="grille_data",
    kind="data",
    provides=[
        codes_de_lannee, lundi_affiche, semaine_affichee, creer_classe_vide,
        sauver_grille, poser_case, annuler_derniere_grille, poser_exception,
        retirer_exception, regler_horaire, classe_id_de,
    ],
    uses=["db", "annees"],
)
