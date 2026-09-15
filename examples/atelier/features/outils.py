"""features/outils — page : quels outils servent, lesquels échouent.

Trois blocs, dans l'ordre où ils répondent :

1. **Les outils de la couche 7** — ``describe``, ``check``, ``probe`` ont
   été construits pour éviter des allers-retours. La part de tâches où
   ils servent dit s'ils y arrivent. C'est le bloc qui a motivé l'app :
   on peut livrer une couche entière et continuer à ouvrir les fichiers
   à la main.
2. **Le taux d'échec par outil** — « où ça plante ».
3. **Les commandes rejouées à l'identique** — la trace la plus nette du
   tâtonnement : relancer la même chose en espérant un autre verdict.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.features.outils_data import (
    echecs,
    par_outil,
    rejoues,
    usage_framework,
)
from examples.atelier.features.shell import shell


def bloc(titre: str, aide: str) -> None:
    ui.heading(titre, level=3)
    ui.text(aide, size="sm", color="muted")


def pourcent_cell(value, _row):
    """Un taux d'échec, peint dès qu'il cesse d'être anecdotique."""
    return ui.text(f"{value} %", size="sm",
                   color="error" if value >= 5 else "muted")


@page("/outils", title="Outils", layout=shell)
def outils_page() -> None:
    """Ce que j'utilise, et ce qui me résiste."""
    # Pas d'`overflow-y-auto` : la coque le fait. Deux régions imbriquées
    # font deux barres, dont une minuscule.
    with ui.vstack(gap="lg"):
        ui.heading("Les outils", level=1)

        bloc(
            "La couche 7 sert-elle ?",
            "`describe`, `check` et `probe` existent pour éviter des "
            "allers-retours. La part de tâches où ils apparaissent dit "
            "s'ils y arrivent — un outil jamais appelé n'évite rien.",
        )
        with ui.hstack(gap="md", wrap=True):
            for ligne in usage_framework():
                with ui.card(classes="flex-1 min-w-48"), ui.vstack(gap="xs"):
                    ui.text(ligne["outil"], size="sm", weight="medium")
                    ui.text(f"{ligne['part']} %", size="2xl", weight="bold")
                    ui.text(
                        f"{ligne['appels']} appels, sur {ligne['taches']} tâches",
                        size="xs", color="muted",
                    )

        bloc("Où ça plante", "Le taux d'échec de chaque outil.")
        ui.table(
            columns=[
                ui.column("outil", label="Outil"),
                ui.column("appels", label="Appels", align="right"),
                ui.column("erreurs", label="Erreurs", align="right"),
                ui.column("taux", label="Taux", align="right",
                          render=pourcent_cell),
            ],
            rows=par_outil()[:14],
            row_key="outil",
        )

        bloc(
            "Les commandes rejouées",
            "La même commande relancée trois fois ou plus dans une seule "
            "tâche. Une deuxième exécution après correction est normale ; "
            "cinq ne le sont pas.",
        )
        with ui.vstack(gap="xs"):
            for ligne in rejoues():
                with ui.hstack(gap="sm", align="center"):
                    ui.badge(f"×{ligne['n']}", color="warning",
                             variant="soft", size="xs")
                    ui.link(f"tâche {ligne['tache_id']}",
                            href=f"/tache/{ligne['tache_id']}")
                    ui.text(ligne["commande"], size="xs", color="muted",
                            classes="flex-1 min-w-0 truncate font-mono")

        bloc("Les derniers échecs", "Ce qui a levé, et sur quoi.")
        with ui.vstack(gap="xs"):
            for ligne in echecs(30):
                with ui.hstack(gap="sm", align="center"):
                    ui.badge(ligne["outil"], color="error", variant="soft",
                             size="xs")
                    ui.link(f"tâche {ligne['tache_id']}",
                            href=f"/tache/{ligne['tache_id']}")
                    ui.text(ligne["detail"] or ligne["commande"] or "—",
                            size="xs", color="muted",
                            classes="flex-1 min-w-0 truncate font-mono")


feature = Feature(
    name="outils",
    kind="page",
    uses=["outils_data", "shell"],
    provides=[outils_page],
)
