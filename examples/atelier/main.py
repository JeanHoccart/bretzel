"""L'atelier — le framework se regarde travailler. ``py -m examples.atelier.main``.

Sa mécanique, en une phrase : **rendre visible comment une tâche a été
menée**. Pas ce qui a été produit — le dépôt le montre déjà — mais le
GESTE : combien de lectures avant d'écrire, combien de fois la suite a
été relancée, quelles commandes ont été rejouées à l'identique, quels
outils ont échoué.

Pourquoi elle existe
--------------------
Demandée le 2026-09-12 : « je voudrais un moyen de constater les méthodes
describe, lint… pour évaluer la performance de ce que tu utilises, où tu
plantes, où tu es lent, pourquoi tu n'y arrives pas du premier coup ».

Une impression ne se discute pas. Une mesure, si. L'app lit les
transcripts de session — ce que Claude Code écrit déjà, sans rien
instrumenter — et en tire une lecture par TÂCHE : un message de
l'utilisateur jusqu'à la réponse finale.

La règle qu'elle mesure
------------------------
Posée le même jour : « tu lis, tu comprends, ensuite tu codes tout, tu
fais le check, tu corriges, et un seul dernier — deux checks globaux, pas
plus, pas d'aller-retour incessant ». C'est
``core/phases.CYCLES_MAX``, et chaque tâche est jugée dessus.

Ce qu'elle exerce du framework
-------------------------------
Une ``ui.datatable`` en mode callable sur 1 856 tâches et 34 000 appels,
une page routée par paramètre qui se partage, un document gelé, et des
états adressables. Comme ``crm``, elle sert deux fois : elle répond à une
question ET elle met le socle sous contrainte.

``main`` est le seul fichier à connaître l'instance : il ``include`` les
features et sème la base au premier démarrage.
"""

from __future__ import annotations

from bretzel import Bretzel
from examples.atelier.core import db, epoque, ingest, perimetre, phases
from examples.atelier.core.db import init_db, is_seeded
from examples.atelier.core.theme import THEME
from examples.atelier.features import (
    outils,
    outils_data,
    phases_page,
    sessions,
    shell,
    tache_detail,
    taches,
    taches_data,
)

app = Bretzel(
    title="Bretzel · Atelier",
    secret_key="dev-atelier-secret-change-me",
    mode="dev",
    theme=THEME,
)

app.include(
    db,                       # infra — le fichier SQLite et ses portes
    phases,                   # logic — le classement d'un appel
    epoque,                   # logic — depuis quand une tâche compte
    perimetre,                # logic — sur QUOI la tâche a travaillé
    ingest,                   # job — l'aspiration des transcripts
    shell,                    # layout — la coque et sa région
    taches_data, outils_data,                       # data
    taches, tache_detail, phases_page, outils, sessions,   # pages
)


@app.startup
async def prepare() -> None:
    """Créer le schéma, et aspirer si la base est vide.

    ⚠️ On n'aspire QUE si rien n'est là. Relire 516 Mo à chaque démarrage
    rendrait `reload=True` inutilisable, et la base ne périme pas : une
    session déjà lue ne change plus. Pour rafraîchir après du travail,
    c'est ``py -m examples.atelier.core.ingest``, explicitement.
    """
    init_db()
    if not is_seeded():
        from examples.atelier.core.ingest import ingest_all

        ingest_all(reset=False)


def main() -> None:
    app.run(port=8018, reload=True)


if __name__ == "__main__":
    main()
