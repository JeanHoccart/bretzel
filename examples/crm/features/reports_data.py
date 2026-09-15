"""features/reports_data — data : les agrégats des rapports, en SQL.

Sert l'écran 7. Chacune de ces cinq lectures est un ``GROUP BY`` — aucune ne
charge de lignes pour compter en Python. C'est le point de l'écran : les 17
apps nourrissent leurs graphiques avec des listes fabriquées à la main, donc
la question « est-ce qu'un chart tient sur un vrai agrégat ? » n'a jamais été
posée.

Toutes les lectures sont bornées : un axe catégoriel ne se lit plus au-delà
d'une dizaine de barres, et un nuage de 50 000 points est une tache.
"""

from __future__ import annotations

from datetime import timedelta

from bretzel import Feature
from examples.crm.core.db import owner_scope, query
from examples.crm.core.domain import OPEN_STAGES, TODAY


def pipeline_by_stage_and_owner(
    owner: str | None, top_owners: int = 3
) -> list[dict]:
    """Le montant ouvert par (étape, propriétaire) — la matrice du bar chart.

    Bornée aux ``top_owners`` plus gros porteurs : une barre groupée par
    propriétaire devient illisible au-delà de trois ou quatre séries, et le
    graphique n'est pas un tableau.
    """
    placeholders = ",".join("?" * len(OPEN_STAGES))
    if owner is not None:
        # Cadré : une seule série, et le « top » n'a plus d'objet.
        owners = [owner]
    else:
        owners = [
            r["owner"] for r in query(
                f"SELECT owner, SUM(amount) AS total FROM deals "
                f"WHERE stage IN ({placeholders}) "
                f"GROUP BY owner ORDER BY total DESC LIMIT ?",
                (*OPEN_STAGES, top_owners),
            )
        ]
    if not owners:
        return []
    return query(
        f"SELECT stage, owner, SUM(amount) AS total FROM deals "
        f"WHERE stage IN ({placeholders}) "
        f"AND owner IN ({','.join('?' * len(owners))}) "
        f"GROUP BY stage, owner",
        (*OPEN_STAGES, *owners),
    )


def activities_by_month(owner: str | None,
                        months: int = 12) -> list[dict]:
    """Le nombre d'activités par mois, du plus ancien au plus récent.

    ``substr(at, 1, 7)`` plutôt que ``strftime`` : les dates sont stockées en
    ISO, donc les sept premiers caractères SONT le mois — et un préfixe de
    chaîne se groupe sans convertir 60 000 lignes en date.
    """
    since = (TODAY - timedelta(days=31 * months)).isoformat()
    # Le premier du mois est calculé PAR LA REQUÊTE : le graphique a besoin
    # d'une date, pas de la chaîne « 2026-08 » qu'il lirait comme une
    # catégorie — et convertir 12 lignes en Python aurait posé un helper de
    # présentation dans une feature de données.
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    return query(
        "SELECT substr(at, 1, 7) AS mois, substr(at, 1, 7) || '-01' AS jour, "
        "COUNT(*) AS n FROM activities "
        f"WHERE at >= ? AND at <= ?{scope} GROUP BY mois ORDER BY mois",
        (since, TODAY.isoformat(), *scope_params),
    )


def accounts_by_industry(owner: str | None, limit: int = 8) -> list[dict]:
    """La répartition des comptes par secteur, les plus gros d'abord."""
    scope, scope_params = owner_scope(owner, "WHERE owner = ? ")
    return query(
        "SELECT industry, COUNT(*) AS n FROM accounts "
        f"{scope}GROUP BY industry ORDER BY n DESC LIMIT ?",
        (*scope_params, limit),
    )


def arr_versus_contacts(owner: str | None,
                        sample: int = 250) -> list[dict]:
    """Un échantillon (nombre de contacts, ARR) — le nuage de corrélation.

    L'échantillon est pris **avant** la jointure, dans une sous-requête :
    plafonner après l'agrégation ferait grouper les 50 000 comptes avec leurs
    120 000 contacts pour n'en garder que 250.

    ⚠️ C'était ``WHERE a.id <= ?``, ce qui n'est un échantillon que si les
    identifiants n'ont pas de trou — et surtout, cadré par propriétaire, ça
    ne rendait qu'un sixième des points. Un ``LIMIT`` dans la sous-requête
    garde la propriété de perf et reste juste dans les deux cas.
    """
    scope, scope_params = owner_scope(owner, "WHERE owner = ? ")
    return query(
        "SELECT a.arr, COUNT(c.id) AS contacts FROM "
        f"(SELECT id, arr FROM accounts {scope}ORDER BY id LIMIT ?) a "
        "LEFT JOIN contacts c ON c.account_id = a.id "
        "GROUP BY a.id",
        (*scope_params, sample),
    )


def weekly_activity(owner: str | None, weeks: int = 12) -> list[int]:
    """Le volume d'activité des ``weeks`` dernières semaines, dans l'ordre.

    Renvoie une liste d'entiers — la forme que ``ui.sparkline`` attend, et la
    seule des cinq qui n'a pas d'axe : une sparkline montre une allure, pas
    des valeurs. Les semaines vides sont RÉINSÉRÉES à zéro : un ``GROUP BY``
    ne rend pas les trous, et une courbe qui les saute raccourcit le temps.
    """
    since = TODAY - timedelta(weeks=weeks)
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(
        "SELECT strftime('%Y-%W', at) AS semaine, COUNT(*) AS n "
        f"FROM activities WHERE at >= ? AND at <= ?{scope} GROUP BY semaine",
        (since.isoformat(), TODAY.isoformat(), *scope_params),
    )
    counts = {r["semaine"]: r["n"] for r in rows}
    # ``weeks + 1`` seaux : la fenêtre SQL part de ``TODAY - 12 semaines`` et
    # va jusqu'à aujourd'hui, donc elle en couvre TREIZE — la première est
    # partielle, la dernière est la semaine en cours. S'arrêter à douze
    # jetait 485 activités sur 12 761 mesurées, et le total affiché sous la
    # sparkline était cet écart-là.
    out: list[int] = []
    for offset in range(weeks + 1):
        day = since + timedelta(weeks=offset)
        out.append(counts.get(f"{day.year}-{day.strftime('%W')}", 0))
    return out


feature = Feature(
    name="reports_data",
    kind="data",
    provides=[pipeline_by_stage_and_owner, activities_by_month,
              accounts_by_industry, arr_versus_contacts, weekly_activity],
    uses=["db"],
)
