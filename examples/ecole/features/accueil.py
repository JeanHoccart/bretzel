"""features/accueil — page: one tile per class (EF-C1).

*"On the doorstep, 20 seconds"* is the first of the specification's four
moments of use. This screen is that one: every class, its size, and
**what is left to review**, without a click.

The "to review" mark is the only element that is not identity data. It
exists *"so it is seen without opening every sheet"* (EF-H4) — a tile not
carrying it would force one to go through thirty pupils to discover there
was nothing.

⚠️ **It held the root in batch 1, it moved down in batch 3.** The
specification gives the opening to the timetable (§ 8); as long as the
grid did not exist, a root returning 404 would have been worse. The move
was announced in this docstring, and it cost one line.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from examples.ecole.core.domain import CYCLES
from examples.ecole.features.annees import AnneeVue, annee_regardee
from examples.ecole.features.classes_data import classes_de, total_eleves
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import bandeau_des_rappels


def tuile(classe: dict) -> None:
    """A class: its code, its size, what is left to review.

    The code is large and the school's label below it: it is "4e1" the
    teacher looks for, not "Quatrième 1".

    The ``href=`` arrived in batch 4, with the screen it opens — not
    before. A tile clickable to a route that does not exist is the
    specification's trap no. 14, *"writing a screen before its routes"*,
    and it costs a bug hunt where there is no bug.
    """
    with (
        ui.card(padding="md", href=f"/classe/{classe['id']}"),
        ui.vstack(gap="sm"),
    ):
        with ui.hstack(justify="between", align="center"):
            ui.heading(classe["code"], level=2, size="xl")
            if classe["a_voir"]:
                # ``xl`` and not the default: ``ui.badge``'s five sizes
                # spread below the current text size, and only the last
                # reaches it. EF-U3's 19 px floor that had made this one
                # the choice went away on 2026-09-12; the choice stays,
                # for the reason that outlives it — a "to review" mark
                # cannot be the smallest word on the card. Cf. F1 of the
                # work.
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
    """Every class of the year being LOOKED AT.

    A zone and not a direct render: changing year in the sidebar must
    change what is here, and a page rendered once would no longer move.
    ``deps=[AnneeVue]`` is the only wire between the two.
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
        # EF-I: the two reminders, COMPUTED on demand. They are at the
        # top of the home page because it is the evening screen, and they
        # do not show at all when there is nothing to say.
        bandeau_des_rappels()
        grille_des_classes()


feature = Feature(
    name="accueil",
    kind="page",
    provides=[accueil_page],
    uses=["classes_data", "annees", "shell", "suivi"],
)
