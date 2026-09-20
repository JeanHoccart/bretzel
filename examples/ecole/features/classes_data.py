"""features/classes_data — data: the class and pupil reads.

``kind="data"``: no page, no rendering. It translates the home page's
questions into SQL and returns dicts. The screens never touch
``core.db``.

**Every read takes its ``annee_id`` as a parameter**, the way the CRM
makes them take their ``owner``: the scoping must show in the signature
one re-reads. A function calling ``annee_regardee()`` on its own would
make the scoping invisible at the call site, and a forgotten path would
stay so.
"""

from __future__ import annotations

from bretzel import Feature
from examples.ecole.core.db import query, scalar


def classes_de(annee_id: int) -> list[dict]:
    """A year's classes, with their size and what is left to review.

    A single query for the tile's three pieces of information (EF-C1) —
    code, size, "to review" mark. At three queries per class, a home page
    with sixteen tiles would make forty-eight.

    ⚠️ ``COUNT(DISTINCT …)`` and not ``COUNT(…)``: joining TWO
    one-to-many tables multiplies the rows by each other. A class of
    thirty pupils with four pending checks would return a size of 120,
    and the home page's total would be wrong the same way — with no
    error, just a plausible number.

    ``i.fin IS NULL``: only pupils with a CURRENT enrolment count. A
    pupil who has left keeps their row (RT-2) and leaves the lists.
    """
    return query(
        """
        SELECT c.id, c.code, c.libelle, c.cycle, c.niveau, c.prof_principal,
               COUNT(DISTINCT i.eleve_id) AS effectif,
               COUNT(DISTINCT v.id)       AS a_voir
        FROM classes c
        LEFT JOIN inscriptions i
               ON i.classe_id = c.id AND i.fin IS NULL
        LEFT JOIN verifications v
               ON v.classe_id = c.id AND v.fait_le IS NULL
        WHERE c.annee_id = ?
        GROUP BY c.id
        ORDER BY c.rang, c.code
        """,
        (annee_id,),
    )


def total_eleves(annee_id: int) -> int:
    """The number of pupils enrolled over the year (EF-C1).

    Recounted in SQL rather than summed from :func:`classes_de`: both
    would answer the same today, and the day a pupil is enrolled in two
    classes of the same year — a repeater reassigned mid-year — the sum
    of the sizes would count them twice.
    """
    return scalar(
        """
        SELECT COUNT(DISTINCT i.eleve_id)
        FROM inscriptions i
        JOIN classes c ON c.id = i.classe_id
        WHERE c.annee_id = ? AND i.fin IS NULL
        """,
        (annee_id,),
    ) or 0


feature = Feature(
    name="classes_data",
    kind="data",
    provides=[classes_de, total_eleves],
    uses=["db"],
)
