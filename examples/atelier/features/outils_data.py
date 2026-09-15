"""features/outils_data — data : le repo des outils et de leurs échecs.

Deux questions, deux requêtes :

- **quels outils, et lesquels échouent** — c'est « où ça plante » ;
- **est-ce que les outils du FRAMEWORK servent** — ``describe``,
  ``check``, ``probe`` ont été construits pour éviter des allers-retours ;
  s'ils ne sont jamais appelés, ils ne peuvent rien éviter.

La seconde est celle qui a motivé l'app : on peut livrer une couche 7
entière et continuer à ouvrir les fichiers à la main.

⚠️ Toutes les lectures passent par les VUES (``taches_epoque``,
``appels_epoque``, ``sessions_epoque``), jamais par les tables — cf.
:mod:`core.epoque`. Gaté par ``test_atelier_epoque``.
"""

from __future__ import annotations

from bretzel import Feature
from examples.atelier.core.db import query, scalar

#: Les trois portes de la couche 7, reconnues dans une commande. Le motif
#: est celui qu'on tape vraiment : ``py -m bretzel.cli.main describe …``.
OUTILS_FRAMEWORK = {
    "describe": "%cli.main describe%",
    "check": "%cli.main check%",
    "probe": "%cli.main probe%",
}


def par_outil() -> list[dict]:
    """Chaque outil : combien d'appels, combien d'échecs, quelle part."""
    rows = query(
        "SELECT outil, COUNT(*) n, SUM(erreur) e FROM appels_epoque "
        "GROUP BY outil ORDER BY n DESC"
    )
    return [
        {
            "outil": r["outil"],
            "appels": r["n"],
            "erreurs": r["e"] or 0,
            "taux": round(100 * (r["e"] or 0) / r["n"], 1) if r["n"] else 0.0,
        }
        for r in rows
    ]


def echecs(limite: int = 60) -> list[dict]:
    """Les derniers appels en échec — « où tu plantes », littéralement."""
    return [
        dict(r)
        for r in query(
            "SELECT a.outil, a.phase, a.commande, a.detail, a.tache_id, "
            "t.session_id FROM appels_epoque a JOIN taches_epoque t ON t.id = a.tache_id "
            "WHERE a.erreur = 1 ORDER BY a.id DESC LIMIT ?",
            (limite,),
        )
    ]


def usage_framework() -> list[dict]:
    """Combien de fois chaque outil de la couche 7 a servi.

    Comparé au nombre de TÂCHES et non d'appels : la question n'est pas
    « combien de fois » dans l'absolu, c'est « sur quelle part du travail
    est-ce que je m'en sers ».
    """
    taches = scalar("SELECT COUNT(*) FROM taches_epoque") or 1
    out = []
    for nom, motif in OUTILS_FRAMEWORK.items():
        appels = scalar(
            "SELECT COUNT(*) FROM appels_epoque WHERE commande LIKE ?", (motif,)
        ) or 0
        touchees = scalar(
            "SELECT COUNT(DISTINCT tache_id) FROM appels_epoque WHERE commande LIKE ?",
            (motif,),
        ) or 0
        out.append({
            "outil": nom,
            "appels": appels,
            "taches": touchees,
            "part": round(100 * touchees / taches, 1),
        })
    return out


def rejoues(limite: int = 25) -> list[dict]:
    """Les commandes relancées À L'IDENTIQUE dans une même tâche.

    C'est la trace la plus nette du tâtonnement : relancer la même chose
    en espérant un autre verdict. Une deuxième exécution après une
    correction est normale ; cinq ne le sont pas.
    """
    return [
        dict(r)
        for r in query(
            "SELECT commande, tache_id, COUNT(*) n FROM appels_epoque "
            "WHERE commande <> '' GROUP BY tache_id, commande "
            "HAVING n >= 3 ORDER BY n DESC LIMIT ?",
            (limite,),
        )
    ]


def profil_session() -> list[dict]:
    """Une ligne par session : de quoi voir si le rythme s'améliore.

    ⚠️ Les totaux sont RECALCULÉS sur les tâches de l'époque, pas lus
    dans les colonnes de ``sessions`` : celles-ci comptent la session
    entière, donc une session à cheval sur le jalon afficherait quarante
    tâches pour cinq lignes visibles.
    """
    return [
        dict(r)
        for r in query(
            "SELECT s.id, s.debut, s.minutes, s.echanges, "
            "(SELECT COUNT(*) FROM taches_epoque WHERE session_id = s.id) taches, "
            "(SELECT SUM(appels) FROM taches_epoque WHERE session_id = s.id) appels, "
            "(SELECT SUM(erreurs) FROM taches_epoque WHERE session_id = s.id) erreurs, "
            "(SELECT AVG(cycles) FROM taches_epoque WHERE session_id = s.id) cycles, "
            "(SELECT COUNT(*) FROM taches_epoque WHERE session_id = s.id "
            " AND verdict = 'du premier coup') premier "
            "FROM sessions_epoque s ORDER BY s.debut DESC"
        )
    ]


feature = Feature(
    name="outils_data",
    kind="data",
    uses=["db"],
    provides=[par_outil, echecs, usage_framework, rejoues, profil_session],
)
