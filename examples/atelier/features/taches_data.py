"""features/taches_data — data : le repo des tâches, en SQL.

Le cœur est :func:`load_taches`, le ``rows=`` callable de la
``ui.datatable`` : il reçoit un ``Query`` (tri, page, recherche, filtres)
et le traduit en UNE requête. 1 856 tâches et 34 000 appels, donc le tier
liste — qui charge tout en Python à chaque frappe — ne tiendrait pas.

Les deux gardes, les mêmes que dans le CRM et pour les mêmes raisons :

- ``sort_key`` et les clés de filtre passent par une **liste blanche**
  avant d'entrer dans le SQL. Une clé de tri vient du navigateur ;
  interpolée telle quelle, c'est une injection ;
- ``filters[cle] == []`` (tout décoché) doit matcher ZÉRO ligne, pas
  « pas de filtre ». Les deux cas se ressemblent assez pour qu'on se
  trompe.

⚠️ Toutes les lectures passent par les VUES (``taches_epoque``,
``appels_epoque``, ``sessions_epoque``), jamais par les tables : c'est
là que vit la coupure de :mod:`core.epoque`, et une requête qui
s'adresserait à la table compterait en silence des tâches d'avant les
instruments. Gaté par ``test_atelier_epoque``.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature
from bretzel.components import Query
from examples.atelier.core.db import query, scalar
from examples.atelier.core.perimetre import APP
from examples.atelier.core.phases import PHASES

#: Les colonnes qu'on accepte de trier. Tout le reste retombe sur le
#: défaut — une clé inconnue ne doit pas atteindre le SQL.
TRIABLES = {
    "debut", "minutes", "appels", "erreurs", "cycles", "jetons",
    "verdict", "session_id", "ordre", "perimetre",
}

#: ⚠️ La clause qui réduit tout aux APPS. Elle vit ici, une seule fois :
#: c'est la question posée — « je ne veux pas évaluer le temps passé sur
#: le framework, je veux ta performance sur les apps » — et deux copies
#: finiraient par ne plus dire la même chose.
APPS_SEULEMENT = f"perimetre LIKE '{APP}%'"

#: Les verdicts possibles, pour le filtre. Recopiés depuis
#: :func:`phases.verdict` — si l'un change, la gate de cohérence des
#: exemples le dira avant l'écran.
VERDICTS = ("du premier coup", "corrigé", "aller-retour")


def where_clause(q: Query) -> tuple[str, list[Any]]:
    """Le ``WHERE`` et ses paramètres — jamais d'interpolation de valeur."""
    clauses: list[str] = []
    params: list[Any] = []
    if q.search:
        clauses.append("(demande LIKE ? OR session_id LIKE ?)")
        motif = f"%{q.search}%"
        params += [motif, motif]
    perimetres = q.filters.get("perimetre")
    if perimetres is not None:
        if not perimetres:
            return "WHERE 1 = 0", []
        clauses.append(f"perimetre IN ({','.join('?' * len(perimetres))})")
        params += list(perimetres)
    verdicts = q.filters.get("verdict")
    if verdicts is not None:
        if not verdicts:
            # Tout décoché = aucune ligne. Sans ce cas, un filtre vide se
            # lirait « pas de filtre » et rendrait la table entière.
            return "WHERE 1 = 0", []
        clauses.append(f"verdict IN ({','.join('?' * len(verdicts))})")
        params += list(verdicts)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def load_taches(q: Query) -> tuple[list[dict], int]:
    """Une page de tâches, et le total qui la situe."""
    where, params = where_clause(q)
    cle = q.sort_key if q.sort_key in TRIABLES else "debut"
    sens = "ASC" if q.sort_dir == "asc" else "DESC"
    total = scalar(f"SELECT COUNT(*) FROM taches_epoque {where}", tuple(params)) or 0

    limite = "" if q.for_export else "LIMIT ? OFFSET ?"
    bornes = [] if q.for_export else [q.per_page, (q.page - 1) * q.per_page]
    rows = query(
        f"SELECT id, session_id, ordre, debut, minutes, demande, appels, "
        f"erreurs, cycles, frise, verdict, jetons, perimetre, lu_avant, "
        f"surface, contrat FROM taches_epoque {where} "
        f"ORDER BY {cle} {sens}, id {sens} {limite}",
        tuple(params + bornes),
    )
    return [dict(r) for r in rows], int(total)


def tache(tache_id: int) -> dict | None:
    """Une tâche par son identifiant — ``None`` si elle n'existe pas."""
    rows = query("SELECT * FROM taches_epoque WHERE id = ?", (tache_id,))
    return dict(rows[0]) if rows else None


def appels_de(tache_id: int) -> list[dict]:
    """Les appels d'une tâche, dans l'ordre où ils ont été faits."""
    return [
        dict(r)
        for r in query(
            "SELECT ordre, horaire, outil, phase, commande, erreur, detail "
            "FROM appels_epoque WHERE tache_id = ? ORDER BY ordre",
            (tache_id,),
        )
    ]


def resume(apps_seulement: bool = False) -> dict[str, Any]:
    """Les nombres du haut d'écran, pour tout ou pour les APPS seules.

    ⚠️ Le drapeau n'est pas un confort d'affichage : mélanger les deux
    rend le chiffre faux dans les deux sens. Construire le socle demande
    de le lire en entier et de le vérifier souvent — du travail sain qui
    ressemble à de l'aller-retour. Écrire une app avec le framework ne
    devrait presque rien exiger ; si ça en exige, c'est la promesse du
    framework qui ne tient pas, ou moi qui ne m'en sers pas.
    """
    ou = f"WHERE {APPS_SEULEMENT}" if apps_seulement else ""
    total = scalar(f"SELECT COUNT(*) FROM taches_epoque {ou}") or 0
    if not total:
        return {"taches": 0, "premier_coup": 0, "part_premier_coup": 0,
                "cycles_moyens": 0.0, "appels": 0, "erreurs": 0,
                "sessions": 0, "surface": 0, "contrat": 0, "lu_avant": 0}
    et = "AND" if ou else "WHERE"
    premier = scalar(
        f"SELECT COUNT(*) FROM taches_epoque {ou} {et} verdict = 'du premier coup'"
    ) or 0
    return {
        "sessions": scalar("SELECT COUNT(*) FROM sessions_epoque") or 0,
        "taches": total,
        "appels": scalar(f"SELECT SUM(appels) FROM taches_epoque {ou}") or 0,
        "erreurs": scalar(f"SELECT SUM(erreurs) FROM taches_epoque {ou}") or 0,
        "premier_coup": premier,
        "part_premier_coup": round(100 * premier / total),
        "cycles_moyens": round(
            scalar(f"SELECT AVG(cycles) FROM taches_epoque {ou}") or 0, 1
        ),
        # Les trois gestes de MÉTHODE, en part de tâches. C'est la
        # réponse à « est-ce que les outils servent, ou décorent ».
        "lu_avant": round(
            100 * (scalar(f"SELECT SUM(lu_avant) FROM taches_epoque {ou}") or 0) / total
        ),
        "surface": round(
            100 * (scalar(f"SELECT SUM(surface) FROM taches_epoque {ou}") or 0) / total
        ),
        "contrat": round(
            100 * (scalar(f"SELECT SUM(contrat) FROM taches_epoque {ou}") or 0) / total
        ),
    }


def par_perimetre() -> list[dict]:
    """Une ligne par périmètre — la comparaison que l'utilisateur demande."""
    return [
        dict(r)
        for r in query(
            "SELECT perimetre, COUNT(*) taches, ROUND(AVG(cycles), 2) cycles, "
            "SUM(verdict = 'du premier coup') premier, "
            "SUM(surface) surface, SUM(contrat) contrat, SUM(lu_avant) lu "
            "FROM taches_epoque GROUP BY perimetre HAVING taches >= 2 "
            "ORDER BY taches DESC"
        )
    ]


def perimetres_connus() -> list[str]:
    """Les périmètres réellement présents — pour le filtre de la table."""
    return [
        r["perimetre"]
        for r in query(
            "SELECT perimetre, COUNT(*) n FROM taches_epoque GROUP BY perimetre "
            "HAVING n >= 2 ORDER BY n DESC"
        )
    ]


def par_phase() -> list[dict]:
    """La répartition des appels par phase — le profil de travail.

    ⚠️ ``autre`` en fait partie et n'est pas caché : c'est le taux d'aveu
    de l'heuristique. S'il grossit, c'est le classement qu'il faut
    corriger, pas la mesure qu'il faut croire.
    """
    total = scalar("SELECT COUNT(*) FROM appels_epoque") or 1
    compte = {
        r["phase"]: r["n"]
        for r in query("SELECT phase, COUNT(*) n FROM appels_epoque GROUP BY phase")
    }
    return [
        {
            "phase": phase,
            "appels": compte.get(phase, 0),
            "part": round(100 * compte.get(phase, 0) / total, 1),
        }
        for phase in PHASES
    ]


feature = Feature(
    name="taches_data",
    kind="data",
    uses=["db", "phases", "perimetre"],
    provides=[load_taches, tache, appels_de, resume, par_phase,
              par_perimetre, perimetres_connus],
)
