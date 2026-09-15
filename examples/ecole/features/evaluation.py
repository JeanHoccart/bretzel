"""features/evaluation — page : la saisie des notes d'un devoir.

EF-D4 à EF-D7. **C'est l'écran du soir**, celui où trente notes se
tapent d'affilée, et c'est le seul de l'application où la frappe est
l'ennemi au sens propre.

⚠️ Le seul endroit de l'app qui écrit un ``name=`` à la main
--------------------------------------------------------------
La règle 4 du funnel dit : *« pas de ``name=`` manuel sur un champ de
formulaire — ``value=binding`` et l'autoname dérive le nom »*. Un binding
est un CHAMP DÉCLARÉ d'une classe d'état, et **on ne peut pas déclarer
trente champs pour trente élèves qu'on ne connaît qu'à l'exécution**.

La sortie de secours est celle que le framework fournit : un ``name=``
dérivé de la clé de ligne, et :func:`~bretzel.state.form_value` pour le
relire. Sa propre fiche dit pourtant qu'elle est faite pour *« des
valeurs transitoires qui ne méritent pas leur état typé — un jeton
CAPTCHA, une confirmation de mot de passe »*, et que *« pour ce qui a une
structure, on préfère un état typé »*. Trente notes ont une structure.

C'est le finding F3 du chantier, dans sa forme la plus coûteuse : la
règle a raison partout où le nombre de champs est connu à l'écriture, et
n'a rien à proposer là où il ne l'est pas. Écrit ici plutôt que contourné
en silence.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, abort, page, refreshable, ui
from bretzel.state import PageState, field, form_value
from examples.ecole.core.domain import TYPES_SUR_COPIE
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.eleves_data import eleves_de
from examples.ecole.features.notes_data import (
    NoteRefuseeError,
    competences_evaluees_de,
    competences_proposees,
    evaluation,
    marquer_reporte,
    moyenne_de_classe,
    notes_de,
    poser_competences,
    poser_note,
    poser_sous_note,
    repartition,
    sous_notes_de,
)
from examples.ecole.features.shell import shell


class VueEvaluation(PageState):
    """L'évaluation ouverte. La page sème, les zones lisent (cf. F4)."""

    evaluation_id: int = field(default=0)


class CompetencesDraft(PageState):
    """La répartition des points, ouverte dans son dialogue (EF-D3)."""

    ouvert: bool = field(default=False)
    evaluation_id: int = field(default=0)


def nom_du_champ(prefixe: str, *cles: int) -> str:
    """Le ``name=`` d'un champ de ligne — une seule façon de le former.

    Une seule fonction pour l'écrire ET le relire : deux littéraux à
    quinze lignes d'écart finiraient par diverger d'un tiret, et le
    symptôme serait « la saisie ne s'enregistre pas », sans erreur.
    """
    return "_".join([prefixe, *(str(c) for c in cles)])


def enregistrer_notes() -> None:
    """La saisie de masse d'EF-D4 : trente notes en un envoi.

    Un seul formulaire et un seul aller-retour. Trente actions séparées
    coûteraient trente requêtes et rendraient la frappe hachée — or *« la
    frappe est l'ennemi »* est le besoin nommé par le cahier pour ce
    moment d'usage.

    ⚠️ **Une ligne refusée n'annule pas les autres.** Les refus sont
    ramassés et dits ensemble ; ce qui est valide est écrit. L'inverse —
    tout ou rien — ferait reperdre vingt-neuf saisies pour une faute de
    frappe.
    """
    donnees = evaluation(int(VueEvaluation().evaluation_id))
    if donnees is None:
        return
    annee_id = donnees["annee_id"]
    bareme = float(donnees["bareme"])
    detaillee = competences_evaluees_de(donnees["id"])
    refus: list[str] = []

    for ligne in eleves_de(donnees["classe_id"]):
        eleve_id = ligne["id"]
        qui = f"{ligne['nom']} {ligne['prenom']}"
        absent = form_value(nom_du_champ("absent", eleve_id),
                            cast=bool, default=False)
        try:
            if detaillee:
                for competence in detaillee:
                    brut = form_value(
                        nom_du_champ("sc", eleve_id, competence["id"]),
                        default="")
                    if brut in ("", None):
                        continue
                    poser_sous_note(donnees["id"], eleve_id, annee_id,
                                    competence["id"], float(brut),
                                    float(competence["points"]))
                if absent:
                    poser_note(donnees["id"], eleve_id, annee_id, True, None,
                               bareme)
                continue
            brut = form_value(nom_du_champ("note", eleve_id), default="")
            if absent:
                poser_note(donnees["id"], eleve_id, annee_id, True, None,
                           bareme)
            elif brut not in ("", None):
                poser_note(donnees["id"], eleve_id, annee_id, False,
                           float(brut), bareme)
        except NoteRefuseeError as refus_metier:
            refus.append(f"{qui} : {refus_metier}")
        except ValueError:
            refus.append(f"{qui} : « {brut} » n'est pas un nombre.")

    if refus:
        # EF-D5 : *« le refus est expliqué à l'écran »*. Un message qui
        # dirait seulement « enregistrement refusé » obligerait à
        # comparer trente lignes pour trouver laquelle.
        ui.notification(" · ".join(refus[:3]), variant="error", title=
                        f"{len(refus)} note(s) refusée(s)", duration_ms=8000)
        return
    ui.notification("Notes enregistrées", variant="success", duration_ms=2000)


def reporter(evaluation_id: int) -> None:
    marquer_reporte(evaluation_id, annee_regardee()["id"])
    ui.notification("Marquée reportée sur École Directe", variant="success",
                    duration_ms=2000)


def ouvrir_competences(evaluation_id: int) -> None:
    draft = CompetencesDraft()
    draft.evaluation_id = evaluation_id
    draft.ouvert = True


def fermer_competences(draft: CompetencesDraft) -> None:
    draft.ouvert = False


def enregistrer_competences(draft: CompetencesDraft) -> None:
    """Le barème DEVIENT la somme des points (EF-D3)."""
    donnees = evaluation(int(draft.evaluation_id))
    if donnees is None:
        return
    points = {
        code: float(form_value(nom_du_champ("pt", 0) + "_" + code,
                               default="0") or 0)
        for code, _lib in competences_proposees(donnees["cycle"],
                                                donnees["type"])
    }
    total = poser_competences(donnees["id"], donnees["annee_id"], points,
                              donnees["cycle"])
    draft.ouvert = False
    ui.notification(
        f"Barème verrouillé à {total:g} — la somme des points répartis."
        if total else "Aucun point réparti : le barème reste libre.",
        variant="success", duration_ms=3000)


@refreshable(deps=[AnneeVue, VueEvaluation, CompetencesDraft])
def saisie() -> None:
    donnees = evaluation(int(VueEvaluation().evaluation_id))
    if donnees is None:
        return
    fige = en_consultation()
    eleves = eleves_de(donnees["classe_id"])
    deja = notes_de(donnees["id"])
    detaillee = competences_evaluees_de(donnees["id"])
    sous = sous_notes_de(donnees["id"]) if detaillee else {}

    with ui.vstack(gap="lg"):
        entete_devoir(donnees, detaillee, fige)
        with ui.card(padding="lg"), ui.vstack(gap="md"):
            ui.heading("Saisie des notes", level=2, size="lg")
            if detaillee:
                ui.text(
                    "Évaluation détaillée : on saisit les sous-notes, et la "
                    "note globale se calcule. Elle n'est jamais saisie.",
                    color="muted",
                )
            with ui.form(on_submit=enregistrer_notes), ui.vstack(gap="sm"):
                for ligne in eleves:
                    ligne_de_saisie(ligne, deja, detaillee, sous,
                                    float(donnees["bareme"]), fige)
                with ui.hstack(justify="end"):
                    ui.button("Enregistrer les notes", type="submit",
                              color="primary", icon_left="save",
                              disabled=fige)
        histogramme(donnees)


def ligne_de_saisie(ligne: dict, deja: dict, detaillee: list[dict],
                    sous: dict, bareme: float, fige: bool) -> None:
    eleve_id = ligne["id"]
    note = deja.get(eleve_id, {})
    with ui.hstack(gap="md", align="center", wrap=True,
                   classes="py-1 border-b border-text/5"):
        ui.text(f"{ligne['nom'].upper()} {ligne['prenom']}",
                classes="min-w-56")
        if detaillee:
            for competence in detaillee:
                with ui.form_field(label=f"{competence['code']} "
                                         f"/{competence['points']:g}"):
                    # Pas de ``max=`` non plus : même raison qu'en
                    # dessous — une sous-note au-dessus de ses points doit
                    # être refusée avec sa phrase, pas rabotée.
                    ui.number_input(
                        name=nom_du_champ("sc", eleve_id, competence["id"]),
                        value=sous.get((eleve_id, competence["id"])),
                        min=0, step=0.5, disabled=fige,
                    )
            ui.text(
                f"= {note.get('valeur'):g}" if note.get("valeur") is not None
                else "= —",
                weight="semibold",
            )
        else:
            with ui.form_field(label=f"Note /{bareme:g}"):
                # ⚠️ **Pas de ``max=``, et c'est EF-D5.** Un plafond posé
                # sur le champ RABOTE silencieusement : on tape 999, le
                # navigateur écrit 20, et personne n'apprend rien. Le
                # cahier demande que la note soit REFUSÉE *et que le refus
                # soit expliqué à l'écran* — donc la valeur doit atteindre
                # la règle métier. Corriger en douce ce que quelqu'un a
                # tapé est la forme d'erreur qu'on ne voit jamais.
                ui.number_input(name=nom_du_champ("note", eleve_id),
                                value=note.get("valeur"), min=0,
                                step=0.5, disabled=fige)
        ui.checkbox(name=nom_du_champ("absent", eleve_id), label="Absent",
                    checked=bool(note.get("absent")), disabled=fige)


def entete_devoir(donnees: dict, detaillee: list[dict], fige: bool) -> None:
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.heading(donnees["nom"], level=1, size="2xl")
                ui.text(
                    f"{donnees['type']} · {donnees['date']} · "
                    f"sur {donnees['bareme']:g} · coefficient "
                    f"{donnees['coefficient']:g}",
                    color="muted",
                )
            with ui.hstack(gap="sm", wrap=True):
                if donnees["reporte_le"]:
                    ui.badge(label=f"reporté le {donnees['reporte_le']}",
                             color="success", variant="soft", size="xl",
                             icon_left="check")
                elif not fige:
                    ui.button("Marquer reportée", variant="outline",
                              icon_left="upload",
                              on_click=partial(reporter, donnees["id"]))
                if not fige:
                    ui.button(
                        "Répartir sur les compétences", variant="outline",
                        icon_left="target",
                        on_click=partial(ouvrir_competences, donnees["id"]))
        if detaillee:
            with ui.hstack(gap="sm", wrap=True):
                for competence in detaillee:
                    ui.badge(
                        label=f"{competence['libelle']} "
                              f"({competence['points']:g} pts)",
                        variant="outline", size="xl")
            ui.text(
                "Le barème est verrouillé : il vaut la somme des points "
                "répartis.",
                color="muted",
            )


def histogramme(donnees: dict) -> None:
    """EF-D6 — la répartition et la moyenne de la classe."""
    tranches = repartition(donnees["id"], float(donnees["bareme"]))
    moyenne = moyenne_de_classe(donnees["id"])
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="baseline", wrap=True):
            ui.heading("Répartition", level=2, size="lg")
            ui.text(
                f"Moyenne de la classe : {moyenne:.2f} / "
                f"{donnees['bareme']:g}" if moyenne is not None
                else "Aucune note saisie",
                color="muted",
            )
        if any(t["value"] for t in tranches):
            ui.bar_chart(data=tranches, color="primary", show_values=True,
                         show_legend=False)
        else:
            ui.empty_state(title="Rien à montrer pour l'instant",
                           icon="chart-column")


@refreshable(deps=[CompetencesDraft])
def dialogue_competences() -> None:
    draft = CompetencesDraft()
    donnees = evaluation(int(draft.evaluation_id))
    if donnees is None:
        return
    proposees = competences_proposees(donnees["cycle"], donnees["type"])
    posees = {c["code"]: c["points"] for c in
              competences_evaluees_de(donnees["id"])}
    with (
        ui.dialog(open=draft.ouvert, title="Répartir les points",
                  on_close=fermer_competences),
        ui.form(on_submit=enregistrer_competences),
        ui.vstack(gap="md"),
    ):
        ui.text(
            f"{len(proposees)} compétences pour ce cycle. Le barème "
            f"deviendra leur somme, et le champ se verrouillera."
            + (" Un devoir sur copie écarte ce qui ne se juge pas sur copie."
               if donnees["type"] in TYPES_SUR_COPIE else ""),
            color="muted",
        )
        for code, libelle in proposees:
            with ui.form_field(label=libelle):
                ui.number_input(name=nom_du_champ("pt", 0) + "_" + code,
                                value=posees.get(code, 0), min=0, max=40,
                                step=1)
        with ui.hstack(justify="end"):
            ui.button("Verrouiller le barème", type="submit", color="primary")


@page("/evaluation/{evaluation_id}", layout=shell, title="Évaluation")
def evaluation_page(evaluation_id: int) -> None:
    donnees = evaluation(int(evaluation_id))
    if donnees is None:
        abort(404)
    vue = VueEvaluation()
    if int(vue.evaluation_id) != int(evaluation_id):
        vue.evaluation_id = int(evaluation_id)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            ui.breadcrumb_item(label=donnees["code"],
                               href=f"/classe/{donnees['classe_id']}")
            ui.breadcrumb_item(label=donnees["nom"])
        saisie()
    dialogue_competences()


feature = Feature(
    name="evaluation",
    kind="page",
    provides=[evaluation_page, VueEvaluation, CompetencesDraft, nom_du_champ],
    uses=["notes_data", "eleves_data", "annees", "shell"],
)
