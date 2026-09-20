"""features/appreciations — the tiles, the text, the review, the summary.

EF-E1 to EF-E9 and EF-F1 to EF-F4. Three surfaces, one feature:

- a pupil's **panel** (tiles + comment), mounted in their sheet;
- a class's **Bilan tab** (EF-F);
- the **review screen** ``/appreciations/{classe_id}`` (EF-E9), which is
  a page of its own because it is a separate moment of use: *"at the end
  of term, two hours, reading in bulk"*.

The rule that decides everything, and it is invisible
------------------------------------------------------
EF-E3: *"as soon as the teacher writes their own text, the application
never rewrites it again"*. On screen, that means one and the same gesture
— ticking a tile — does two different things depending on the sheet's
history. The screen SAYS so, because a behaviour that changes with no
explanation reads as a failure.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, abort, page, refreshable, ui
from bretzel.state import PageState, field, form_value
from examples.ecole.core.redaction import LIMITE, bilan, rediger
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.appreciations_data import (
    FichesRev,
    cocher,
    criteres_et_niveaux,
    ecrire_a_la_main,
    fiche_de,
    fiches_de_classe,
    phrase_du_niveau,
    proposer,
    redemander,
    teintes_de_classe,
)
from examples.ecole.features.eleves_data import classe, eleves_de
from examples.ecole.features.notes_data import notes_du_trimestre
from examples.ecole.features.shell import shell
from examples.ecole.features.vue_classe import VueClasse

#: A tile's tint, in WHOLE strings — never assembled, for the reason
#: written in ``emploi_du_temps.py``: a class built in an f-string only
#: exists in development.
TEINTES: dict[int, str] = {
    1: "border-success text-success",
    2: "border-info text-info",
    3: "border-warning text-warning",
    4: "border-error text-error",
}
TEINTE_COCHEE: dict[int, str] = {
    1: "bg-success/15 border-success",
    2: "bg-info/15 border-info",
    3: "bg-warning/15 border-warning",
    4: "bg-error/15 border-error",
}


class VueEleveFiche(PageState):
    """The pupil whose sheet is being filled, and their class. The page
    seeds."""

    eleve_id: int = field(default=0)
    classe_id: int = field(default=0)
    trimestre: int = field(default=1)


def moyenne_pour(eleve_id: int, classe_id: int, trimestre: int) -> float | None:
    """A term's average, by § 5.2's single rule."""
    from examples.ecole.core.domain import moyenne_de

    lignes = notes_du_trimestre(eleve_id, classe_id, trimestre)
    return moyenne_de([(li["valeur"], li["bareme"], li["coefficient"])
                       for li in lignes if not li["absent"]])


def texte_propose(eleve_id: int, classe_id: int, trimestre: int) -> str:
    """Compose EF-E2's comment from what is known of the pupil.

    Three inputs, and the specification names them: *"the ticked
    observations, the term's marks, and the change between terms"*. The
    third is what forces reading the PREVIOUS term too.
    """
    fiche = fiche_de(eleve_id, classe_id, trimestre)
    observations = {
        critere: (phrase_du_niveau(donnees["niveau_id"], trimestre),
                  donnees["teinte"])
        for critere, donnees in fiche["niveaux"].items()
    }
    return rediger(
        trimestre=trimestre,
        observations=observations,
        moyenne=moyenne_pour(eleve_id, classe_id, trimestre),
        moyenne_precedente=(moyenne_pour(eleve_id, classe_id, trimestre - 1)
                            if trimestre > 1 else None),
    )


# ── Les handlers ─────────────────────────────────────────────────────

def basculer(critere_id: int, niveau_id: int, deja_coche: bool) -> None:
    """Tick or untick a tile, then REPROPOSE the text (EF-E2).

    *"Ticking an observation reproposes a comment"* — but ``proposer``
    refuses if the teacher has written (EF-E3), and it is that function
    that carries the refusal, not this one.
    """
    vue = VueEleveFiche()
    annee_id = annee_regardee()["id"]
    eleve_id, classe_id = int(vue.eleve_id), int(vue.classe_id)
    trimestre = int(vue.trimestre)
    cocher(eleve_id, classe_id, trimestre, annee_id, critere_id,
           None if deja_coche else niveau_id)
    proposer(eleve_id, classe_id, trimestre, annee_id,
             texte_propose(eleve_id, classe_id, trimestre))


def enregistrer_texte() -> None:
    """The teacher writes: the flag falls PERMANENTLY (EF-E3)."""
    vue = VueEleveFiche()
    ecrire_a_la_main(int(vue.eleve_id), int(vue.classe_id),
                     int(vue.trimestre), annee_regardee()["id"],
                     str(form_value("appreciation", default="")))
    ui.notification(
        "Texte enregistré. L'application ne le réécrira plus ; le bouton "
        "« Reproposer » est là pour revenir en arrière.",
        variant="success", duration_ms=4000)


def reproposer() -> None:
    """EF-E3's button — the only way of handing back to the factory."""
    vue = VueEleveFiche()
    annee_id = annee_regardee()["id"]
    eleve_id, classe_id = int(vue.eleve_id), int(vue.classe_id)
    trimestre = int(vue.trimestre)
    redemander(eleve_id, classe_id, trimestre, annee_id)
    proposer(eleve_id, classe_id, trimestre, annee_id,
             texte_propose(eleve_id, classe_id, trimestre))


# ── A pupil's panel ──────────────────────────────────────────────────

def rangee_de_tuiles(bloc: dict, cochee: dict, fige: bool) -> None:
    """A row of EF-E1: a criterion, its levels, a single tick.

    *"The tile's tint says whether it is favourable (1-2) or a difficulty
    (3-4)."* So the colour is not decorative: it is the only information
    read at a glance across thirty sheets.
    """
    choisie = cochee.get(bloc["critere"], {}).get("niveau_id")
    with ui.vstack(gap="sm"):
        ui.text(bloc["critere"], weight="semibold")
        with ui.hstack(gap="sm", wrap=True):
            for niveau in bloc["niveaux"]:
                active = niveau["id"] == choisie
                ui.button(
                    niveau["court"],
                    variant="outline",
                    disabled=fige,
                    classes=(TEINTE_COCHEE if active else TEINTES)[
                        niveau["teinte"]],
                    tooltip=niveau["long"],
                    on_click=partial(basculer, bloc["critere_id"],
                                     niveau["id"], active),
                )


# ``FichesRev`` in the deps, and it is what was missing: ticking a tile
# only writes to the DATABASE, so without a revision token the zone never
# re-renders and the proposed text stays invisible.
@refreshable(deps=[AnneeVue, VueEleveFiche, FichesRev])
def panneau_appreciation() -> None:
    vue = VueEleveFiche()
    eleve_id, classe_id = int(vue.eleve_id), int(vue.classe_id)
    trimestre = int(vue.trimestre)
    if not (eleve_id and classe_id):
        return
    fiche = fiche_de(eleve_id, classe_id, trimestre)
    fige = en_consultation()
    texte = fiche["appreciation"]

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading(f"Observations · trimestre {trimestre}", level=2,
                   size="lg")
        for bloc in criteres_et_niveaux():
            rangee_de_tuiles(bloc, fiche["niveaux"], fige)

        ui.divider(label="Appréciation")
        # EF-E3: the behaviour changes with the sheet's history, and
        # the screen SAYS so. A gesture that does not have the same
        # effect twice running with no explanation reads as a failure.
        ui.banner(
            message=(
                "Texte écrit à la main : cocher une observation ne le "
                "réécrira plus. « Reproposer » rend la main à "
                "l'application."
                if fiche["ecrite_main"] else
                "Texte proposé par l'application : il se refait à chaque "
                "observation cochée, jusqu'à ce que vous écriviez le vôtre."
            ),
            color="info" if fiche["ecrite_main"] else "secondary",
            icon="pen-line" if fiche["ecrite_main"] else "sparkles",
            size="lg",
        )
        with ui.form(on_submit=enregistrer_texte), ui.vstack(gap="sm"):
            ui.textarea(name="appreciation", value=texte, rows=4,
                        maxlength=LIMITE, disabled=fige)
            with ui.hstack(gap="md", justify="between", align="center",
                           wrap=True):
                # EF-E4: the counter, because 400 is a hard limit and
                # one writes blind without it.
                ui.text(f"{len(texte)} / {LIMITE} caractères",
                        color="error" if len(texte) > LIMITE else "muted")
                with ui.hstack(gap="sm"):
                    ui.button("Reproposer", variant="ghost",
                              icon_left="sparkles", disabled=fige,
                              on_click=reproposer)
                    ui.button("Enregistrer mon texte", type="submit",
                              color="primary", icon_left="save",
                              disabled=fige)


# ── A class's Bilan tab (EF-F) ───────────────────────────────────────

@refreshable(deps=[AnneeVue, VueClasse, FichesRev])
def panneau_bilan() -> None:
    vue = VueClasse()
    classe_id, trimestre = int(vue.classe_id), int(vue.trimestre)
    eleves = eleves_de(classe_id)
    moyennes = [m for m in (moyenne_pour(e["id"], classe_id, trimestre)
                            for e in eleves) if m is not None]
    texte = bilan(moyennes=moyennes,
                  teintes_par_critere=teintes_de_classe(classe_id, trimestre))

    with ui.vstack(gap="md"):
        with ui.card(padding="lg"), ui.vstack(gap="md"):
            ui.heading(f"Bilan du trimestre {trimestre}", level=2, size="lg")
            ui.text(texte)
            # EF-F2: the summary STARTS from what dominates and
            # presents the difficulty as a nuance. The screen cannot
            # guarantee that — the factory does — but it can say why it
            # keeps quiet when it keeps quiet (EF-F4).
            ui.text(
                f"{len(moyennes)} moyenne(s) disponible(s) sur "
                f"{len(eleves)} élèves.",
                color="muted",
            )
        with ui.card(padding="lg"), ui.vstack(gap="md"):
            ui.heading("Répartition des moyennes", level=3, size="md")
            if moyennes:
                ui.bar_chart(
                    data=[
                        {"label": "< 9",
                         "value": sum(1 for m in moyennes if m < 9)},
                        {"label": "9 – 13",
                         "value": sum(1 for m in moyennes if 9 <= m < 13)},
                        {"label": "13 – 15",
                         "value": sum(1 for m in moyennes if 13 <= m < 15)},
                        {"label": "≥ 15",
                         "value": sum(1 for m in moyennes if m >= 15)},
                    ],
                    color="primary", show_values=True, show_legend=False,
                )
            else:
                ui.empty_state(title="Aucune moyenne ce trimestre",
                               icon="chart-column")
        ui.link(label="Relire toutes les appréciations",
                href=f"/appreciations/{classe_id}?t={trimestre}",
                variant="underline")


# ── The review screen (EF-E9) ────────────────────────────────────────

class VueRelecture(PageState, addressable=True):
    """The class and the term being reviewed. The term lives in the
    address."""

    classe_id: int = field(default=0)
    trimestre: int = field(default=1, url="t")


@refreshable(deps=[AnneeVue, VueRelecture, FichesRev])
def liste_de_relecture() -> None:
    vue = VueRelecture()
    classe_id, trimestre = int(vue.classe_id), int(vue.trimestre)
    lignes = fiches_de_classe(classe_id, trimestre)

    with ui.vstack(gap="md"):
        ui.text(
            f"{sum(1 for li in lignes if li['appreciation'])} appréciation(s) "
            f"rédigée(s) sur {len(lignes)} élèves.",
            color="muted",
        )
        for ligne in ui.each(lignes, key="eleve_id"):
            with ui.card(padding="md"), ui.vstack(gap="sm"):
                with ui.hstack(justify="between", align="center", wrap=True):
                    ui.link(
                        label=f"{ligne['nom'].upper()} {ligne['prenom']}",
                        href=f"/eleve/{ligne['eleve_id']}?t={trimestre}",
                        variant="underline")
                    with ui.hstack(gap="sm", align="center"):
                        if ligne["ecrite_main"]:
                            ui.badge(label="écrite à la main", size="xl",
                                     variant="outline", icon_left="pen-line")
                        # EF-E9: *"with each one's character counter"*.
                        # It is what is re-read at the end of term — a
                        # comment that is too long is truncated by École
                        # Directe, not refused.
                        ui.text(
                            f"{len(ligne['appreciation'])} / {LIMITE}",
                            color="error"
                            if len(ligne["appreciation"]) > LIMITE
                            else "muted",
                        )
                ui.text(ligne["appreciation"] or "— pas encore rédigée",
                        color=None if ligne["appreciation"] else "muted")


@page("/appreciations/{classe_id}", layout=shell, title="Appréciations")
def relecture_page(classe_id: int) -> None:
    donnees = classe(int(classe_id))
    if donnees is None:
        abort(404)
    vue = VueRelecture()
    if int(vue.classe_id) != int(classe_id):
        vue.classe_id = int(classe_id)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            ui.breadcrumb_item(label=donnees["code"],
                               href=f"/classe/{classe_id}")
            ui.breadcrumb_item(label="Appréciations")
        ui.heading(f"Appréciations · {donnees['code']}", level=1, size="2xl")
        ui.text(
            "L'écran de la fin de trimestre : on relit tout d'affilée, et "
            "chaque texte porte son compte de caractères.",
            color="muted",
        )
        liste_de_relecture()


feature = Feature(
    name="appreciations",
    kind="page",
    provides=[relecture_page, panneau_appreciation, panneau_bilan,
              VueEleveFiche, VueRelecture, texte_propose],
    uses=["appreciations_data", "notes_data", "eleves_data", "annees",
          "shell", "vue_classe"],
)
