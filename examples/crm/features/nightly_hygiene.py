"""features/nightly_hygiene — job : la passe d'hygiène nocturne.

Feature ``kind="job"`` : une tâche de fond. Pas de route, pas de rendu,
aucun `Request` — c'est ce que le kind déclare, et c'est pour ça qu'un
job n'ancre PAS le placement optimal dans la carte d'app (seules les
pages et les layouts ancrent). Branchée sur un ordonnanceur dans une
vraie app ; exposée comme fonction ici, pour qu'elle soit appelable et
testable sans horloge.

Ce qu'elle fait est le besoin réel d'un CRM : les affaires ouvertes dont
la date de clôture est passée sont du bruit dans le pipeline. Personne
ne les ferme pendant sa journée, donc la nuit s'en charge — elle les
COMPTE et les rend, elle ne décide pas à la place d'un commercial.

Reprise du recalcul nocturne de l'app `mad` le 2026-09-10, quand elle
a été retirée : `job` n'était exercé que là. La couverture
est gatée depuis, par
``tests/consistency/test_every_feature_kind_is_exercised.py``.
"""

from __future__ import annotations

from bretzel import Feature
from examples.crm.core.db import query
from examples.crm.core.domain import OPEN_STAGES, TODAY


def stale_deals() -> list[dict]:
    """Les affaires OUVERTES dont la date de clôture est dépassée.

    Sans cadrage de portefeuille : un job tourne sans utilisateur, donc
    il n'a pas d'identité à qui restreindre la lecture. C'est
    exactement la raison pour laquelle
    ``test_crm_owned_reads_declare_their_scope`` porte une liste blanche
    nommée plutôt qu'une règle aveugle.
    """
    marques = ", ".join("?" for _ in OPEN_STAGES)
    return query(
        f"SELECT id, name, owner, stage, close_date FROM deals "
        f"WHERE stage IN ({marques}) AND close_date < ? "
        f"ORDER BY close_date",
        (*OPEN_STAGES, TODAY.isoformat()),
    )


def run_nightly_hygiene() -> int:
    """La passe complète — rend le nombre d'affaires à revoir."""
    return len(stale_deals())


feature = Feature(
    name="nightly_hygiene",
    kind="job",
    provides=[run_nightly_hygiene, stale_deals],
    uses=["db"],
)
