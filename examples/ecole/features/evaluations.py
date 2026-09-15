"""features/evaluations — l'onglet « Évaluations » d'une classe.

EF-D1 et EF-D2 : la liste d'un trimestre, et la création — y compris
*« donner le même devoir à plusieurs classes d'un même niveau d'un
coup »*.

⚠️ Ce n'est pas une PAGE. C'est le panneau que ``features/classe.py``
monte dans son second onglet, et son contrat le dit : ``kind="logic"``,
aucun ``@page``. Le découper ainsi évite que ``classe.py`` grossisse d'un
lot à l'autre jusqu'à devenir illisible — ce que le cahier appelle *une
feature qu'on n'a pas nommée*.
"""

from __future__ import annotations

from datetime import date
from functools import partial

from bretzel import Feature, redirect, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import TYPES_EVALUATION, niveau_du_code
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.eleves_data import classe, classes_de
from examples.ecole.features.notes_data import (
    creer_evaluation,
    donner_a_plusieurs,
    evaluations_de,
)
from examples.ecole.features.vue_classe import VueClasse


class EvaluationDraft(PageState):
    """Le brouillon de création d'un devoir (EF-D2)."""

    ouvert: bool = field(default=False)
    classe_id: int = field(default=0)
    trimestre: int = field(default=1)
    nom: str = field(default="")
    type: str = field(default="DS")
    date: str = field(default="")
    bareme: float = field(default=20.0)
    coefficient: float = field(default=1.0)
    tout_le_niveau: bool = field(default=False)


def ouvrir_creation(classe_id: int, trimestre: int) -> None:
    draft = EvaluationDraft()
    draft.classe_id = classe_id
    draft.trimestre = trimestre
    draft.nom = ""
    draft.type = "DS"
    draft.date = date.today().isoformat()
    draft.bareme = 20.0
    draft.coefficient = 1.0
    draft.tout_le_niveau = False
    draft.ouvert = True


def fermer_creation(draft: EvaluationDraft) -> None:
    draft.ouvert = False


def enregistrer_creation(draft: EvaluationDraft) -> None:
    """Crée le devoir — dans une classe, ou dans tout son niveau.

    *« Chacune garde la sienne, reliées entre elles »* (EF-D2) : la date
    peut différer d'une classe à l'autre et les moyennes se calculent par
    classe, donc ce ne sont pas une évaluation partagée mais N évaluations
    qui se savent sœurs.
    """
    annee = annee_regardee()
    classe_id = int(draft.classe_id)
    origine = classe(classe_id)
    if origine is None:
        return
    champs = {
        "trimestre": int(draft.trimestre),
        "nom": str(draft.nom).strip()[:80] or "Évaluation",
        "type": str(draft.type),
        "date": str(draft.date) or date.today().isoformat(),
        "bareme": float(draft.bareme or 20),
        "coefficient": float(draft.coefficient or 1),
    }
    if bool(draft.tout_le_niveau):
        niveau = niveau_du_code(origine["code"])
        soeurs = [
            c["id"] for c in classes_de(annee["id"])
            if niveau_du_code(c["code"]) == niveau
        ]
        # La classe d'origine EN PREMIER : c'est son identifiant qui
        # devient le lien commun, et c'est celle qu'on ouvre après.
        soeurs = [classe_id, *(c for c in soeurs if c != classe_id)]
        identifiants = donner_a_plusieurs(soeurs, annee["id"], champs)
        draft.ouvert = False
        ui.notification(
            f"Devoir créé dans {len(identifiants)} classes de {niveau}",
            variant="success", duration_ms=3000)
        redirect(f"/evaluation/{identifiants[0]}")
        return
    eval_id = creer_evaluation(classe_id, annee["id"], champs)
    draft.ouvert = False
    redirect(f"/evaluation/{eval_id}")


def ligne_evaluation(ligne: dict) -> None:
    """Une ligne d'EF-D1 : tout ce qu'on regarde le soir, sans ouvrir."""
    with (
        ui.card(padding="sm", href=f"/evaluation/{ligne['id']}"),
        ui.hstack(gap="md", align="center", justify="between", wrap=True),
    ):
        with ui.vstack(gap="none"):
            ui.text(ligne["nom"], weight="semibold")
            ui.text(
                f"{ligne['type']} · {ligne['date']} · sur "
                f"{ligne['bareme']:g} · coefficient {ligne['coefficient']:g}",
                color="muted",
            )
        with ui.hstack(gap="sm", align="center", wrap=True):
            if ligne["competences"]:
                ui.badge(label=f"{ligne['competences']} compétences",
                         variant="outline", size="xl")
            if ligne["commune_id"]:
                ui.badge(label="commune au niveau", variant="outline",
                         color="secondary", size="xl",
                         tooltip="Le même devoir dans plusieurs classes")
            # L'avancement de la saisie : la seule colonne de cette liste
            # qui soit un calcul, et celle qu'on cherche des yeux.
            ui.text(f"{ligne['saisies']}/{ligne['effectif']} saisies",
                    color="success" if ligne["saisies"] >= ligne["effectif"]
                    else "muted")
            if ligne["reporte_le"]:
                ui.badge(label=f"reporté le {ligne['reporte_le']}",
                         color="success", variant="soft", size="xl",
                         icon_left="check")
            else:
                ui.badge(label="à reporter", color="warning",
                         variant="soft", size="xl")


# ``VueClasse`` dans les deps, et ce n'est pas facultatif : sans lui,
# changer de trimestre dans le sélecteur laisserait cette liste sur
# le trimestre précédent — l'écran montrerait deux trimestres à la
# fois sans le signaler. C'est le silence B2 de `livrer-une-app.md`.
@refreshable(deps=[AnneeVue, VueClasse, EvaluationDraft])
def panneau_evaluations() -> None:
    """Le panneau de l'onglet. Il lit la classe et le trimestre dans
    ``VueClasse``, qui vit dans sa PROPRE feature : la partager avec
    ``classe.py`` par un import croisé aurait fait un cycle de contrat,
    et ``check --deep`` l'a dit avant qu'il ne s'installe.
    """
    vue = VueClasse()
    classe_id = int(vue.classe_id)
    trimestre = int(vue.trimestre)
    lignes = evaluations_de(classe_id, trimestre)
    fige = en_consultation()

    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.text(f"{len(lignes)} évaluation(s) au trimestre {trimestre}",
                    color="muted")
            if not fige:
                ui.button("Créer une évaluation", icon_left="plus",
                          variant="outline",
                          on_click=partial(ouvrir_creation, classe_id,
                                           trimestre))
        if not lignes:
            ui.empty_state(
                title=f"Aucune évaluation au trimestre {trimestre}",
                icon="clipboard-list",
                description="Le sélecteur de trimestre est au-dessus.",
            )
        for ligne in ui.each(lignes, key="id"):
            ligne_evaluation(ligne)


@refreshable(deps=[EvaluationDraft])
def dialogue_evaluation() -> None:
    draft = EvaluationDraft()
    with (
        ui.dialog(open=draft.ouvert, title="Créer une évaluation",
                  on_close=fermer_creation),
        ui.form(on_submit=enregistrer_creation),
        ui.vstack(gap="md"),
    ):
        with ui.form_field(label="Nom", required=True):
            ui.input(value=draft.nom, placeholder="Contrôle n°2")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Type"):
                ui.select(value=draft.type,
                          options=[(t, t) for t in TYPES_EVALUATION])
            with ui.form_field(label="Date"):
                ui.date_picker(value=draft.date)
            with ui.form_field(label="Barème",
                               hint="Verrouillé par les compétences, après."):
                ui.number_input(value=draft.bareme, min=1, max=100, step=1)
            with ui.form_field(label="Coefficient"):
                ui.number_input(value=draft.coefficient, min=1, max=10,
                                step=1)
        ui.switch(checked=draft.tout_le_niveau,
                  label="Donner à toutes les classes du même niveau")
        ui.text(
            "Chaque classe garde la sienne : la date peut différer et les "
            "moyennes se calculent par classe. Seule l'appartenance au même "
            "devoir est partagée.",
            color="muted",
        )
        with ui.hstack(justify="end"):
            ui.button("Créer", type="submit", color="primary")


feature = Feature(
    name="evaluations",
    kind="logic",
    provides=[panneau_evaluations, dialogue_evaluation, EvaluationDraft],
    uses=["notes_data", "eleves_data", "annees", "vue_classe"],
)
