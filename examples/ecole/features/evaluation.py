"""features/evaluation — page: entering a test's marks.

EF-D4 to EF-D7. **It is the evening screen**, the one where thirty marks
are typed in a row, and it is the app's only one where typing is the
enemy in the literal sense.

⚠️ The app's only place that writes a ``name=`` by hand
---------------------------------------------------------
Rule 4 of the funnel says: *"no manual ``name=`` on a form field —
``value=binding`` and autoname derives the name"*. A binding is a
DECLARED FIELD of a state class, and **one cannot declare thirty fields
for thirty pupils only known at run time**.

The escape hatch is the one the framework provides: a ``name=`` derived
from the row key, and :func:`~bretzel.state.form_value` to read it back.
Its own note says, though, that it is made for *"transient values that do
not deserve their typed state — a CAPTCHA token, a password
confirmation"*, and that *"for anything with a structure, a typed state
is preferred"*. Thirty marks have a structure.

It is the work's finding F3, in its costliest form: the rule is right
everywhere the number of fields is known at writing time, and has nothing
to offer where it is not. Written here rather than worked around in
silence.
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
    """The assessment open. The page seeds, the zones read (cf. F4)."""

    evaluation_id: int = field(default=0)


class CompetencesDraft(PageState):
    """The distribution of points, open in its dialog (EF-D3)."""

    ouvert: bool = field(default=False)
    evaluation_id: int = field(default=0)


def nom_du_champ(prefixe: str, *cles: int) -> str:
    """A row field's ``name=`` — one single way of forming it.

    A single function to write it AND read it back: two literals fifteen
    lines apart would end up diverging by a hyphen, and the symptom would
    be "the entry does not save", with no error.
    """
    return "_".join([prefixe, *(str(c) for c in cles)])


def enregistrer_notes() -> None:
    """EF-D4's bulk entry: thirty marks in one send.

    A single form and a single round trip. Thirty separate actions would
    cost thirty requests and make the typing choppy — and *"typing is the
    enemy"* is the need the specification names for this moment of use.

    ⚠️ **A refused row does not cancel the others.** The refusals are
    collected and said together; what is valid is written. The opposite —
    all or nothing — would lose twenty-nine entries again for one typo.
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
        # EF-D5: *"the refusal is explained on screen"*. A message
        # saying only "save refused" would force comparing thirty rows
        # to find which one.
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
    """The scale BECOMES the sum of the points (EF-D3)."""
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
                    # No ``max=`` either: the same reason as below — a
                    # sub-mark above its points must be refused with its
                    # sentence, not trimmed.
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
                # ⚠️ **No ``max=``, and it is EF-D5.** A ceiling set on
                # the field TRIMS silently: one types 999, the browser
                # writes 20, and nobody learns anything. The
                # specification asks the mark to be REFUSED *and the
                # refusal to be explained on screen* — so the value must
                # reach the business rule. Quietly correcting what
                # somebody typed is the form of error one never sees.
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
    """EF-D6 — the class's distribution and average."""
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
