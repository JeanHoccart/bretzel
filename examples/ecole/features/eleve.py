"""features/eleve — page: a pupil's sheet.

EF-C3: *"their photo, their class, their term marks with their average,
their ticked observations, their comment, their particularities and their
pending checks."*

Seven things, and four arrive with their batch: the marks in 5, the
observations and the comment in 6, the checks in 8. Batch 4 delivers the
three that depend on nothing — the identity, the particularities, and
EF-C9's **path**, which is the only thing on this sheet that nobody else
shows.

Why the path counts more than it seems
---------------------------------------
*"The enrolments are dated precisely for that; without the screen that
shows them, the history is kept and invisible."* RT-2 makes every
departure carry a date instead of erasing a row; this screen is the only
reason that date serves any purpose.
"""

from __future__ import annotations

from bretzel import Feature, abort, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import AMENAGEMENTS, moyenne_de
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.appreciations import (
    VueEleveFiche,
    panneau_appreciation,
)
from examples.ecole.features.eleves_data import (
    classe_courante_de,
    eleve,
    parcours_de,
    regler_particularites,
)
from examples.ecole.features.notes_data import notes_du_trimestre
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import (
    VueSuiviEleve,
    dialogue_verification,
    panneau_verifications,
)


class VueEleve(PageState, addressable=True):
    """The pupil open and the term being looked at (EF-U1).

    The pupil is in the path; only the term needs a URL name, because it
    changes what the server computes. But ``eleve_id`` must live in the
    state anyway: a ``@refreshable`` zone is called back with no
    argument, and the base layer REFUSES it to declare a parameter.
    """

    eleve_id: int = field(default=0)
    trimestre: int = field(default=1, url="t")


class Particularites(PageState):
    """The draft of the four particularities (EF-C4).

    ``eleve_id`` is rendered by no field and arrives anyway: it is a
    declared attribute, so the base layer hydrates it from the POST. It
    serves to detect that the draft speaks of ANOTHER pupil — without
    which opening a second sheet would keep the first one's boxes.
    """

    eleve_id: int = field(default=0)
    amenagement: str = field(default="")
    vue_fragile: bool = field(default=False)
    gaucher: bool = field(default=False)
    precisions: str = field(default="")


def enregistrer_particularites(form: Particularites) -> None:
    regler_particularites(int(form.eleve_id), annee_regardee()["id"], {
        "amenagement": str(form.amenagement),
        "vue_fragile": bool(form.vue_fragile),
        "gaucher": bool(form.gaucher),
        "precisions": str(form.precisions),
    })
    ui.notification("Particularités enregistrées", variant="success",
                    duration_ms=2000)


@refreshable(deps=[AnneeVue, VueEleve, Particularites])
def panneau_particularites() -> None:
    eleve_id = int(VueEleve().eleve_id)
    fiche = eleve(eleve_id)
    if fiche is None:
        return
    form = Particularites()
    if int(form.eleve_id) != eleve_id:
        form.eleve_id = eleve_id
        form.amenagement = fiche["amenagement"]
        form.vue_fragile = bool(fiche["vue_fragile"])
        form.gaucher = bool(fiche["gaucher"])
        form.precisions = fiche["precisions"]
    fige = en_consultation()

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Particularités", level=2, size="lg")
        with ui.form(on_submit=enregistrer_particularites), ui.vstack(gap="md"):
            with ui.form_field(
                label="Aménagement",
                hint="PAP, PPS, PAI, PPRE — vide si aucun.",
            ):
                ui.select(
                    value=form.amenagement, disabled=fige,
                    options=[("", "Aucun"),
                             *((a, a) for a in AMENAGEMENTS)],
                )
            with ui.hstack(gap="lg", wrap=True):
                ui.switch(checked=form.vue_fragile,
                          label="Vue fragile", disabled=fige)
                ui.switch(checked=form.gaucher, label="Gaucher",
                          disabled=fige)
            with ui.form_field(
                label="Précisions",
                hint="Ce qui ne rentre dans aucune case.",
            ):
                ui.textarea(value=form.precisions, rows=3,
                            disabled=fige)
            with ui.hstack(justify="end"):
                ui.button("Enregistrer", type="submit",
                          color="primary", icon_left="save",
                          disabled=fige)


def changer_trimestre_eleve(vue: VueEleve) -> None:
    """Empty: the mutation alone re-renders the ``deps=[VueEleve]``
    zones."""


@refreshable(deps=[AnneeVue, VueEleve])
def panneau_notes() -> None:
    """The term's marks and the AVERAGE (EF-C3).

    The average goes through :func:`~examples.ecole.core.domain.moyenne_de`,
    which carries § 5.2's whole rule: weighted by the coefficient, each
    mark brought back to 20 by its scale, and **absences do not count** —
    they are not worth zero.
    """
    vue = VueEleve()
    eleve_id = int(vue.eleve_id)
    trimestre = int(vue.trimestre)
    courante = classe_courante_de(eleve_id)
    lignes = (notes_du_trimestre(eleve_id, courante["id"], trimestre)
              if courante else [])
    moyenne = moyenne_de([
        (li["valeur"], li["bareme"], li["coefficient"])
        for li in lignes if not li["absent"]
    ])

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="baseline", wrap=True):
            ui.heading("Notes", level=2, size="lg")
            ui.text(
                f"Moyenne : {moyenne:.2f} / 20" if moyenne is not None
                else "Aucune note ce trimestre",
                color="muted",
            )
        ui.toggle_group(
            value=vue.trimestre,
            options=[(1, "Trimestre 1"), (2, "Trimestre 2"),
                     (3, "Trimestre 3")],
            on_change=changer_trimestre_eleve,
        )
        for ligne in ui.each(lignes, key="id"):
            with ui.hstack(gap="md", align="center", justify="between",
                           wrap=True):
                ui.link(label=ligne["nom"],
                        href=f"/evaluation/{ligne['id']}",
                        variant="underline")
                ui.text(f"{ligne['type']} · {ligne['date']}",
                        color="muted")
                if ligne["absent"]:
                    ui.badge(label="absent", color="warning",
                             variant="soft", size="xl")
                elif ligne["valeur"] is None:
                    ui.text("non saisie", color="muted")
                else:
                    ui.text(
                        f"{ligne['valeur']:g} / {ligne['bareme']:g}",
                        weight="semibold")


def panneau_parcours(eleve_id: int) -> None:
    """EF-C9 — the classes gone through, with their dates."""
    etapes = parcours_de(eleve_id)
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Parcours", level=2, size="lg")
        if len(etapes) <= 1:
            ui.text("Une seule inscription : aucun mouvement à montrer.",
                    color="muted")
        for etape in ui.each(etapes, key="debut"):
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.icon("calendar" if etape["fin"] else "calendar-check",
                        color="muted" if etape["fin"] else "success")
                ui.text(etape["annee"], color="muted")
                ui.link(label=etape["code"],
                        href=f"/classe/{etape['classe_id']}",
                        variant="underline")
                ui.text(
                    f"du {etape['debut']} au {etape['fin']}"
                    if etape["fin"] else f"depuis le {etape['debut']}",
                    color="muted",
                )


@page("/eleve/{eleve_id}", layout=shell, title="Élève")
def eleve_page(eleve_id: int) -> None:
    fiche = eleve(int(eleve_id))
    if fiche is None:
        abort(404)
    # The page seeds, the zone reads (cf. ``VueEleve``).
    vue = VueEleve()
    if int(vue.eleve_id) != int(eleve_id):
        vue.eleve_id = int(eleve_id)
    courante = classe_courante_de(int(eleve_id))
    # The observation sheet needs all THREE: the pupil, their class and
    # the term. It is seeded here for the same reason as the rest — a
    # zone re-renders outside the routing (cf. F4).
    observations = VueEleveFiche()
    observations.eleve_id = int(eleve_id)
    observations.classe_id = courante["id"] if courante else 0
    observations.trimestre = int(vue.trimestre)
    VueSuiviEleve().eleve_id = int(eleve_id)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            if courante:
                ui.breadcrumb_item(label=courante["code"],
                                   href=f"/classe/{courante['id']}")
            ui.breadcrumb_item(label=f"{fiche['nom']} {fiche['prenom']}")

        with ui.hstack(gap="lg", align="center", wrap=True):
            ui.avatar(name=f"{fiche['prenom']} {fiche['nom']}", size="xl",
                      shape="circle")
            with ui.vstack(gap="none"):
                ui.heading(f"{fiche['nom'].upper()} {fiche['prenom']}",
                           level=1, size="2xl")
                ui.text(
                    courante["libelle"] if courante
                    else "Aucune inscription en cours",
                    color="muted",
                )

        panneau_notes()
        panneau_verifications()
        panneau_appreciation()
        with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
            panneau_particularites()
            panneau_parcours(int(eleve_id))
    dialogue_verification()


feature = Feature(
    name="eleve",
    kind="page",
    provides=[eleve_page, VueEleve, Particularites],
    uses=["eleves_data", "notes_data", "appreciations", "suivi",
          "annees", "shell"],
)
