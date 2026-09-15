"""features/accueil — page : une tuile par classe (EF-C1).

*« Sur le pas de la porte, 20 secondes »* est le premier des quatre
moments d'usage du cahier. Cet écran est celui-là : toutes les classes,
leur effectif, et **ce qui reste à voir**, sans un clic.

La marque « à voir » est le seul élément qui ne soit pas une donnée
d'identité. Elle existe *« pour qu'on le voie sans ouvrir chaque fiche »*
(EF-H4) — une tuile qui ne la porterait pas obligerait à traverser trente
élèves pour découvrir qu'il n'y avait rien.

⚠️ **Il a tenu la racine au lot 1, il est descendu au lot 3.** Le cahier
donne l'ouverture à l'emploi du temps (§ 8) ; tant que la grille
n'existait pas, une racine en 404 aurait été pire. Le déplacement était
annoncé dans cette docstring, et il a coûté une ligne.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from examples.ecole.core.domain import CYCLES
from examples.ecole.features.annees import AnneeVue, annee_regardee
from examples.ecole.features.classes_data import classes_de, total_eleves
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import bandeau_des_rappels


def tuile(classe: dict) -> None:
    """Une classe : son code, son effectif, ce qui reste à voir.

    Le code est en grand et le libellé de l'établissement en dessous :
    c'est « 4e1 » que le professeur cherche des yeux, pas « Quatrième 1 ».

    Le ``href=`` est arrivé au lot 4, avec l'écran qu'il ouvre — pas
    avant. Une tuile cliquable vers une route inexistante est le piège
    n° 14 du cahier, *« écrire un écran avant ses routes »*, et il coûte
    une recherche de bug là où il n'y en a pas.
    """
    with (
        ui.card(padding="md", href=f"/classe/{classe['id']}"),
        ui.vstack(gap="sm"),
    ):
        with ui.hstack(justify="between", align="center"):
            ui.heading(classe["code"], level=2, size="xl")
            if classe["a_voir"]:
                # ``xl`` et pas le défaut : les cinq tailles de
                # ``ui.badge`` s'étalent en dessous de la taille du
                # texte courant, et seule la dernière l'atteint. Le
                # plancher de 19 px d'EF-U3 qui avait fait choisir
                # celle-ci est parti le 2026-09-12 ; le choix reste,
                # pour la raison qui lui survit — une marque « à
                # voir » ne peut pas être le plus petit mot de la
                # carte. Cf. F1 du chantier.
                ui.badge(
                    label="à voir",
                    color="warning",
                    variant="soft",
                    size="xl",
                    icon_left="clipboard-check",
                )
        ui.text(classe["libelle"], color="muted")
        with ui.hstack(gap="md", align="center"):
            ui.icon("users", color="muted")
            ui.text(f"{classe['effectif']} élèves")
            ui.text("·", color="muted")
            ui.text(CYCLES[classe["cycle"]], color="muted")


@refreshable(deps=[AnneeVue])
def grille_des_classes() -> None:
    """Toutes les classes de l'année REGARDÉE.

    Zone et non rendu direct : changer d'année dans la barre latérale
    doit changer ce qui est ici, et une page rendue une fois ne bougerait
    plus. ``deps=[AnneeVue]`` est le seul câble entre les deux.
    """
    annee = annee_regardee()
    classes = classes_de(annee["id"])

    with ui.vstack(gap="md"):
        with ui.hstack(gap="md", align="baseline", wrap=True):
            ui.heading(f"Mes classes · {annee['libelle']}", level=1,
                       size="2xl")
            ui.text(f"{total_eleves(annee['id'])} élèves en tout",
                    color="muted")
        if not classes:
            ui.empty_state(
                title="Aucune classe sur cette année",
                icon="school",
                description="L'emploi du temps crée les classes au fur et "
                            "à mesure qu'on y tape un code.",
            )
            return
        with ui.grid(min_col="20rem", gap="md"):
            for classe in classes:
                tuile(classe)


PATH = "/classes"


@page(PATH, layout=shell, title="Mes classes")
def accueil_page() -> None:
    with ui.vstack(gap="lg"):
        # EF-I : les deux rappels, CALCULÉS à la demande. Ils sont en
        # haut de l'accueil parce que c'est l'écran du soir, et ils ne
        # s'affichent pas du tout quand il n'y a rien à dire.
        bandeau_des_rappels()
        grille_des_classes()


feature = Feature(
    name="accueil",
    kind="page",
    provides=[accueil_page],
    uses=["classes_data", "annees", "shell", "suivi"],
)
