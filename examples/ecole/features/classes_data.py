"""features/classes_data — data : les lectures de classes et d'élèves.

``kind="data"`` : aucune page, aucun rendu. Elle traduit les questions de
l'accueil en SQL et rend des dicts. Les écrans ne touchent jamais
``core.db``.

**Toute lecture prend son ``annee_id`` en paramètre**, comme le CRM fait
prendre son ``owner`` : le cadrage doit se voir dans la signature qu'on
relit. Une fonction qui appellerait ``annee_regardee()`` toute seule
rendrait le cadrage invisible au call-site, et un chemin oublié le
resterait.
"""

from __future__ import annotations

from bretzel import Feature
from examples.ecole.core.db import query, scalar


def classes_de(annee_id: int) -> list[dict]:
    """Les classes d'une année, avec leur effectif et ce qui reste à voir.

    Une seule requête pour les trois informations de la tuile (EF-C1) —
    code, effectif, marque « à voir ». En trois requêtes par classe, un
    accueil à seize tuiles en ferait quarante-huit.

    ⚠️ ``COUNT(DISTINCT …)`` et pas ``COUNT(…)`` : joindre DEUX tables
    un-à-plusieurs multiplie les lignes entre elles. Une classe de trente
    élèves avec quatre vérifications en attente rendrait un effectif de
    120, et le total de l'accueil serait faux de la même façon — sans
    aucune erreur, juste un nombre crédible.

    ``i.fin IS NULL`` : seuls les élèves EN COURS d'inscription comptent.
    Un élève sorti garde sa ligne (RT-2) et sort des listes.
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
    """Le nombre d'élèves en service sur l'année (EF-C1).

    Recompté en SQL plutôt que sommé depuis :func:`classes_de` : les deux
    répondraient pareil aujourd'hui, et le jour où un élève sera inscrit
    dans deux classes de la même année — un redoublant réaffecté en cours
    d'année — la somme des effectifs le compterait deux fois.
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
