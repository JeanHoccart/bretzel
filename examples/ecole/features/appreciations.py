"""features/appreciations — les tuiles, le texte, la relecture, le bilan.

EF-E1 à EF-E9 et EF-F1 à EF-F4. Trois surfaces, une feature :

- le **panneau d'un élève** (tuiles + appréciation), monté dans sa fiche ;
- l'**onglet Bilan** d'une classe (EF-F) ;
- l'**écran de relecture** ``/appreciations/{classe_id}`` (EF-E9), qui
  est une page à lui seul parce que c'est un moment d'usage à part :
  *« en fin de trimestre, deux heures, la lecture de masse »*.

La règle qui décide de tout, et elle est invisible
---------------------------------------------------
EF-E3 : *« dès que le professeur écrit son propre texte, l'application ne
le réécrit plus jamais »*. À l'écran, ça veut dire qu'un même geste —
cocher une tuile — fait deux choses différentes selon l'histoire de la
fiche. L'écran le DIT, parce qu'un comportement qui change sans
explication se lit comme une panne.
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

#: La teinte d'une tuile, en chaînes ENTIÈRES — jamais assemblées, pour
#: la raison écrite dans ``emploi_du_temps.py`` : une classe construite
#: en f-string n'existe qu'en développement.
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
    """L'élève dont on remplit la fiche, et sa classe. La page sème."""

    eleve_id: int = field(default=0)
    classe_id: int = field(default=0)
    trimestre: int = field(default=1)


def moyenne_pour(eleve_id: int, classe_id: int, trimestre: int) -> float | None:
    """La moyenne d'un trimestre, par la règle unique du § 5.2."""
    from examples.ecole.core.domain import moyenne_de

    lignes = notes_du_trimestre(eleve_id, classe_id, trimestre)
    return moyenne_de([(li["valeur"], li["bareme"], li["coefficient"])
                       for li in lignes if not li["absent"]])


def texte_propose(eleve_id: int, classe_id: int, trimestre: int) -> str:
    """Compose l'appréciation d'EF-E2 depuis ce qu'on sait de l'élève.

    Trois entrées, et le cahier les nomme : *« les observations cochées,
    les notes du trimestre, et l'évolution entre trimestres »*. La
    troisième est ce qui oblige à lire aussi le trimestre PRÉCÉDENT.
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
    """Coche ou décoche une tuile, puis REPROPOSE le texte (EF-E2).

    *« Cocher une observation repropose une appréciation »* — mais
    ``proposer`` refuse si le professeur a écrit (EF-E3), et c'est cette
    fonction-là qui porte le refus, pas celle-ci.
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
    """Le professeur écrit : le drapeau tombe DÉFINITIVEMENT (EF-E3)."""
    vue = VueEleveFiche()
    ecrire_a_la_main(int(vue.eleve_id), int(vue.classe_id),
                     int(vue.trimestre), annee_regardee()["id"],
                     str(form_value("appreciation", default="")))
    ui.notification(
        "Texte enregistré. L'application ne le réécrira plus ; le bouton "
        "« Reproposer » est là pour revenir en arrière.",
        variant="success", duration_ms=4000)


def reproposer() -> None:
    """Le bouton d'EF-E3 — la seule façon de rendre la main à la fabrique."""
    vue = VueEleveFiche()
    annee_id = annee_regardee()["id"]
    eleve_id, classe_id = int(vue.eleve_id), int(vue.classe_id)
    trimestre = int(vue.trimestre)
    redemander(eleve_id, classe_id, trimestre, annee_id)
    proposer(eleve_id, classe_id, trimestre, annee_id,
             texte_propose(eleve_id, classe_id, trimestre))


# ── Le panneau d'un élève ────────────────────────────────────────────

def rangee_de_tuiles(bloc: dict, cochee: dict, fige: bool) -> None:
    """Une rangée d'EF-E1 : un critère, ses niveaux, une seule coche.

    *« La teinte de la tuile dit si c'est favorable (1-2) ou une
    difficulté (3-4). »* La couleur n'est donc pas décorative : c'est la
    seule information qu'on lit en diagonale sur trente fiches.
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


# ``FichesRev`` dans les deps, et c'est ce qui manquait : cocher une
# tuile n'écrit qu'en BASE, donc sans jeton de révision la zone ne se
# re-rend jamais et le texte proposé reste invisible.
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
        # EF-E3 : le comportement change selon l'histoire de la fiche, et
        # l'écran le DIT. Un geste qui n'a pas le même effet d'une fois
        # sur l'autre sans explication se lit comme une panne.
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
                # EF-E4 : le compteur, parce que 400 est une limite dure
                # et qu'on écrit à l'aveugle sans lui.
                ui.text(f"{len(texte)} / {LIMITE} caractères",
                        color="error" if len(texte) > LIMITE else "muted")
                with ui.hstack(gap="sm"):
                    ui.button("Reproposer", variant="ghost",
                              icon_left="sparkles", disabled=fige,
                              on_click=reproposer)
                    ui.button("Enregistrer mon texte", type="submit",
                              color="primary", icon_left="save",
                              disabled=fige)


# ── L'onglet Bilan d'une classe (EF-F) ───────────────────────────────

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
            # EF-F2 : le bilan PART de ce qui domine et présente la
            # difficulté comme une nuance. L'écran ne peut pas garantir
            # ça — c'est la fabrique qui le fait — mais il peut dire
            # pourquoi il se tait quand il se tait (EF-F4).
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


# ── L'écran de relecture (EF-E9) ─────────────────────────────────────

class VueRelecture(PageState, addressable=True):
    """La classe et le trimestre relus. Le trimestre vit dans l'adresse."""

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
                        # EF-E9 : *« avec le compteur de caractères de
                        # chacune »*. C'est ce qu'on relit en fin de
                        # trimestre — une appréciation trop longue est
                        # tronquée par École Directe, pas refusée.
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
