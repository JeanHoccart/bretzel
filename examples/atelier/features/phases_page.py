"""features/phases_page — page : à quoi passe le temps, par phase.

Une seule question : **est-ce que le travail est découpé, ou mélangé ?**
La répartition par phase le dit en quatre barres, et le taux de « non
classé » dit à quel point on peut la croire.

⚠️ La part d'AUTRE est affichée au même rang que les autres, pas rangée
en note de bas de page. C'est le taux d'aveu de l'heuristique : si elle
grossit, c'est le classement qu'il faut corriger, pas la mesure qu'il
faut croire.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.core.perimetre import label as label_perimetre
from examples.atelier.core.phases import AUTRE, CYCLES_MAX, LIBELLES
from examples.atelier.features.outils_data import profil_session
from examples.atelier.features.shell import shell
from examples.atelier.features.taches_data import par_perimetre, par_phase


def cycles_cell(value, _row):
    """Les cycles moyens d'une session, peints par la règle."""
    return ui.text(f"{value:.1f}", size="sm",
                   color="error" if value > CYCLES_MAX else "success")


#: Partagées avec l'écran des sessions : une seule définition de ce qu'on
#: montre d'une session, sinon les deux écrans divergent.
COLONNES_SESSION = [
    ui.column("court", label="Session"),
    ui.column("debut", label="Début"),
    ui.column("taches", label="Tâches", align="right"),
    ui.column("echanges", label="Échanges", align="right"),
    ui.column("appels", label="Appels", align="right"),
    ui.column("erreurs", label="Erreurs", align="right"),
    ui.column("cycles", label="Cycles moyens", align="right",
              render=cycles_cell),
    ui.column("reussite", label="Du premier coup", align="right"),
]


def lignes_session(limite: int | None = None) -> list[dict]:
    """Les sessions, mises en forme pour :data:`COLONNES_SESSION`."""
    lignes = profil_session()
    if limite is not None:
        lignes = lignes[:limite]
    return [
        {
            "id": ligne["id"],
            "court": ligne["id"][:8],
            "debut": (ligne["debut"] or "")[:16].replace("T", " "),
            "taches": ligne["taches"],
            "echanges": ligne["echanges"],
            "appels": ligne["appels"],
            "erreurs": ligne["erreurs"],
            "cycles": ligne["cycles"] or 0,
            "reussite": f"{ligne['premier']}/{ligne['taches']}",
        }
        for ligne in lignes
    ]


COULEURS = {
    "lecture": "info",
    "ecriture": "primary",
    "verification": "warning",
    "livraison": "success",
    "autre": "muted",
}


@page("/phases", title="Phases", layout=shell)
def phases_page() -> None:
    """Le profil de travail, et son évolution par session."""
    répartition = par_phase()

    with ui.vstack(gap="lg"):
        ui.heading("Les phases", level=1)
        ui.text(
            "Chaque appel d'outil est rangé dans une phase. C'est de ce "
            "classement que vient la frise, et donc le jugement porté sur "
            "chaque tâche.",
            color="muted",
        )

        with ui.vstack(gap="sm"):
            for ligne in répartition:
                with ui.hstack(gap="md", align="center"):
                    ui.text(ligne["phase"], size="sm", weight="medium",
                            classes="w-32")
                    ui.progress(value=ligne["part"], max=100,
                                color=COULEURS.get(ligne["phase"], "muted"),
                                classes="flex-1")
                    ui.text(f"{ligne['part']} %", size="sm",
                            classes="w-16 text-right")
                    ui.text(f"{ligne['appels']} appels", size="xs",
                            color="muted", classes="w-28 text-right")
                ui.text(LIBELLES[ligne["phase"]], size="xs", color="muted",
                        classes="pl-36")

        part_autre = next(
            (bloc["part"] for bloc in répartition if bloc["phase"] == AUTRE),
            0.0,
        )
        if part_autre >= 15:
            ui.alert(
                f"{part_autre} % des appels ne sont pas classés. Au-delà "
                "de quelques pour cent, la frise cesse d'être croyable : "
                "c'est l'heuristique de `core/phases.py` qu'il faut "
                "corriger, pas la mesure qu'il faut croire.",
                color="warning",
            )

        ui.heading("Par périmètre", level=3)
        ui.text(
            "La question posée : bâtir le socle demande de le lire en "
            "entier et de le vérifier souvent — du travail sain qui "
            "ressemble à de l'aller-retour. Une app écrite AVEC le "
            "framework ne devrait presque rien exiger. L'écart entre les "
            "deux lignes est la mesure utile.",
            size="sm", color="muted",
        )
        ui.table(
            columns=[
                ui.column("nom", label="Périmètre"),
                ui.column("taches", label="Tâches", align="right"),
                ui.column("cycles", label="Cycles moyens", align="right",
                          render=cycles_cell),
                ui.column("premier", label="Du premier coup", align="right"),
                ui.column("surface", label="`describe` avant", align="right"),
                ui.column("contrat", label="`check --deep`", align="right"),
            ],
            rows=[
                {
                    "nom": label_perimetre(r["perimetre"]),
                    "taches": r["taches"],
                    "cycles": r["cycles"] or 0,
                    "premier": f"{r['premier']}/{r['taches']}",
                    "surface": f"{r['surface']}/{r['taches']}",
                    "contrat": f"{r['contrat']}/{r['taches']}",
                }
                for r in par_perimetre()
            ],
            row_key="nom",
        )

        ui.heading("Par session", level=3)
        ui.text(
            "La même mesure dans le temps : est-ce que le rythme "
            "s'améliore ?",
            size="sm", color="muted",
        )
        ui.table(columns=COLONNES_SESSION, rows=lignes_session(30),
                 row_key="id")


feature = Feature(
    name="phases_page",
    kind="page",
    uses=["taches_data", "outils_data", "shell", "phases", "perimetre"],
    provides=[phases_page],
)
