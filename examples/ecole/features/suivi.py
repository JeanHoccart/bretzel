"""features/suivi — the work to check, the reminders, entering a lesson.

EF-H1 to EF-H4, EF-I1 to EF-I5, EF-B15. Three surfaces, and they match
three different moments of use from § 2:

- the **start-of-lesson frames**, at the head of the timetable: *"on the
  doorstep, 20 seconds"*;
- a pupil sheet's **checks panel**: *"in class, on a tablet"*, where the
  note is set with one finger;
- the **two reminders**, on the home page: what one looks at in the
  evening.

EF-B16 still holds: no "Maintenant" banner
-------------------------------------------
The start-of-lesson frame is NOT the banner removed twice. The difference
is that it carries something readable nowhere else — the last session
held and the work to check — where the banner repeated what the grid
already said better.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import partial

from bretzel import Feature, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import trimestre_de
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.calendrier_data import trimestres_de
from examples.ecole.features.eleves_data import classe_courante_de
from examples.ecole.features.notes_data import corrections_en_attente
from examples.ecole.features.suivi_data import (
    NOMS_AFFICHES,
    SuiviRev,
    derniere_seance,
    eleves_sans_observation,
    marquer_faite,
    notes_non_reportees,
    poser_verification,
    supprimer_verification,
    verifications_de,
    verifications_eleve,
)

#: EF-H2's reasons — *"ticked with one finger, where one thinks of it"*.
#: A closed and short list: a menu of fifteen entries would cost more
#: time than writing the reason by hand.
MOTIFS: tuple[str, ...] = (
    "cahier incomplet", "cahier mal tenu", "travail non fait",
    "exercice à refaire", "signature des parents",
)


class VerifDraft(PageState):
    """The pupil a reminder is being set for."""

    ouvert: bool = field(default=False)
    eleve_id: int = field(default=0)
    classe_id: int = field(default=0)
    nom: str = field(default="")
    motif: str = field(default="")


def debut_du_trimestre(annee: dict, cycle: str) -> tuple[int, date]:
    """The current term and its start date (EF-I4).

    A term's start is never entered: it reads as the day after the
    previous one (EF-A3). It is here that this rule really serves — the
    session count must start from there, not from the start of the school
    year.
    """
    debut_annee = date.fromisoformat(annee["debut"])
    fin_annee = date.fromisoformat(annee["fin"])
    connus = trimestres_de(annee["id"])
    fins = {
        numero: (date.fromisoformat(connus[(cycle, numero)])
                 if connus.get((cycle, numero)) else None)
        for numero in (1, 2, 3)
    }
    numero = trimestre_de(date.today(), fins, fin_annee) or 1
    if numero == 1:
        return 1, debut_annee
    precedent = fins.get(numero - 1)
    # A term's start is the DAY AFTER the end of the previous one
    # (EF-A3): never entered, always derived.
    return numero, (precedent + timedelta(days=1) if precedent
                    else debut_annee)


# ── Les handlers ─────────────────────────────────────────────────────

def ouvrir_verification(eleve_id: int, classe_id: int, nom: str) -> None:
    draft = VerifDraft()
    draft.eleve_id = eleve_id
    draft.classe_id = classe_id
    draft.nom = nom
    draft.motif = MOTIFS[0]
    draft.ouvert = True


def fermer_verification(draft: VerifDraft) -> None:
    draft.ouvert = False


def enregistrer_verification(draft: VerifDraft) -> None:
    poser_verification(int(draft.eleve_id), int(draft.classe_id),
                       annee_regardee()["id"], str(draft.motif))
    draft.ouvert = False


def poser_vite(eleve_id: int, classe_id: int, motif: str) -> None:
    """EF-H2 — *"in a single gesture on a common reason"*.

    No dialog: it is the gesture one makes in class, standing up, and
    every intermediate screen is a note one does not take.
    """
    poser_verification(eleve_id, classe_id, annee_regardee()["id"], motif)


def cocher_faite(verification_id: int) -> None:
    marquer_faite(verification_id, annee_regardee()["id"])


def retirer(verification_id: int) -> None:
    supprimer_verification(verification_id, annee_regardee()["id"])


# ── A pupil's panel (EF-H1, EF-H2, EF-H3) ────────────────────────────

class VueSuiviEleve(PageState):
    """The pupil whose checks are shown. The page seeds."""

    eleve_id: int = field(default=0)


@refreshable(deps=[AnneeVue, VueSuiviEleve, SuiviRev, VerifDraft])
def panneau_verifications() -> None:
    eleve_id = int(VueSuiviEleve().eleve_id)
    if not eleve_id:
        return
    courante = classe_courante_de(eleve_id)
    lignes = verifications_eleve(eleve_id)
    attente = [li for li in lignes if not li["fait_le"]]
    faites = [li for li in lignes if li["fait_le"]]
    fige = en_consultation()

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Travail à vérifier", level=2, size="lg")
        ui.text(
            "Rien ne s'efface quand c'est fait : la date est posée. Trois "
            "cahiers incomplets dans le trimestre disent quelque chose que "
            "trois lignes effacées ne diraient plus.",
            color="muted",
        )
        if courante and not fige:
            with ui.hstack(gap="sm", wrap=True):
                for motif in MOTIFS:
                    ui.button(
                        motif, variant="outline",
                        on_click=partial(poser_vite, eleve_id,
                                         courante["id"], motif),
                    )
        for ligne in ui.each(attente, key="id"):
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.icon("clipboard-check", color="warning")
                ui.text(ligne["motif"], weight="medium")
                ui.text(f"{ligne['code']} · posé le {ligne['cree_le']}",
                        color="muted")
                ui.button("C'est fait", variant="ghost", disabled=fige,
                          on_click=partial(cocher_faite, ligne["id"]))
                # EF-H3: *"a row set BY MISTAKE is deleted — ticking it
                # 'done' would be a lie"*.
                ui.icon_button("trash-2", variant="ghost", disabled=fige,
                               aria_label="Posée par erreur",
                               tooltip="Posée par erreur",
                               on_click=partial(retirer, ligne["id"]))
        if faites:
            ui.divider(label=f"{len(faites)} déjà vérifié(s)")
            for ligne in ui.each(faites, key="id"):
                with ui.hstack(gap="md", align="center", wrap=True):
                    ui.icon("check", color="success")
                    ui.text(ligne["motif"], color="muted")
                    ui.text(f"fait le {ligne['fait_le']}", color="muted")


@refreshable(deps=[VerifDraft])
def dialogue_verification() -> None:
    draft = VerifDraft()
    with (
        ui.dialog(open=draft.ouvert, title=f"Travail à vérifier · {draft.nom}",
                  on_close=fermer_verification),
        ui.form(on_submit=enregistrer_verification),
        ui.vstack(gap="md"),
    ):
        with ui.form_field(label="Motif"):
            ui.input(value=draft.motif)
        with ui.hstack(justify="end"):
            ui.button("Poser le rappel", type="submit", color="primary")


# ── The start-of-lesson frames (EF-B15) ──────────────────────────────

@refreshable(deps=[AnneeVue, SuiviRev])
def cadres_du_jour() -> None:
    """EF-B15's frames: the hour's class, and the next.

    Two things per frame, and **nothing else**:

    - *"what was covered last time, in one line: the SESSION's number and
      title"*. Neither the date, nor the chapter, nor the homework set —
      *"the chapter is the same for six weeks and does not situate the
      class"*;
    - *"the work to check, ticked with one finger, where one thinks of
      it"*.
    """
    from examples.ecole.features.grille_data import (
        lundi_affiche,
        semaine_affichee,
    )

    annee = annee_regardee()
    aujourdhui = date.today()
    semaine = semaine_affichee(annee, lundi_affiche(annee, ""))
    du_jour = next((j for j in semaine["jours"] if j["date"] == aujourdhui),
                   None)
    blocs = [b for b in (du_jour["blocs"] if du_jour else []) if not b["nature"]]
    if not blocs:
        return

    with ui.grid(min_col="20rem", gap="md"):
        for bloc in blocs[:2]:
            cadre_de_classe(bloc["code"], annee)


def cadre_de_classe(code: str, annee: dict) -> None:
    lignes = [c for c in classes_de_lannee(annee["id"]) if c["code"] == code]
    if not lignes:
        return
    donnees = lignes[0]
    derniere = derniere_seance(donnees["id"])
    attente = verifications_de(donnees["id"])

    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.link(label=donnees["code"], href=f"/classe/{donnees['id']}",
                    variant="underline")
            if attente:
                ui.badge(label=f"{len(attente)} à voir", color="warning",
                         variant="soft", size="xl")
        if derniere and derniere["seance_titre"]:
            ui.text(
                f"Séance {derniere['seance_numero']} : "
                f"{derniere['seance_titre']}",
                weight="medium",
            )
        elif derniere and derniere["chapitre"]:
            # The FALLBACK, and nothing else: an hour recorded with no
            # session chosen.
            ui.text(derniere["chapitre"], color="muted")
        else:
            ui.text("Aucune séance consignée pour l'instant.", color="muted")
        for ligne in ui.each(attente[:3], key="id"):
            with ui.hstack(gap="sm", align="center", wrap=True):
                ui.icon("clipboard-check", color="warning")
                ui.text(f"{ligne['prenom']} {ligne['nom'].upper()} — "
                        f"{ligne['motif']}")
                ui.button("Fait", variant="ghost",
                          disabled=en_consultation(),
                          on_click=partial(cocher_faite, ligne["id"]))


def classes_de_lannee(annee_id: int) -> list[dict]:
    """The year's classes — imported here to avoid a cycle."""
    from examples.ecole.features.eleves_data import classes_de

    return classes_de(annee_id)


# ── The two reminders (EF-I) ─────────────────────────────────────────

@refreshable(deps=[AnneeVue, SuiviRev])
def bandeau_des_rappels() -> None:
    """EF-I1, EF-I2 — **computed on demand**, never stored.

    *"Two oversights the application sees coming, computed on demand and
    not kept in a list that would diverge from reality."*
    """
    annee = annee_regardee()
    a_reporter = notes_non_reportees(annee["id"])
    corrections = corrections_en_attente(annee["id"])
    numero, debut = debut_du_trimestre(annee, "college")
    sans_observation = eleves_sans_observation(annee, numero, debut)

    if not (a_reporter or corrections or sans_observation):
        return

    with ui.vstack(gap="sm"):
        for evaluation in ui.each(a_reporter[:4], key="id"):
            ui.banner(
                message=f"{evaluation['code']} · « {evaluation['nom']} » du "
                        f"{evaluation['date']} : "
                        f"{evaluation['saisies']} notes saisies, pas encore "
                        f"marquées reportées sur École Directe.",
                icon="upload", color="warning",
                            size="lg",
            )
        if corrections:
            ui.banner(
                message=f"{len(corrections)} note(s) corrigée(s) après coup "
                        f"restent à reporter à la main.",
                icon="pencil-line", color="warning",
                            size="lg",
            )
        for classe_signalee in ui.each(sans_observation[:3], key="classe_id"):
            ui.banner(
                message=message_sans_observation(classe_signalee, numero),
                icon="clipboard-list", color="info",
                            size="lg",
            )


def message_sans_observation(signalee: dict, trimestre: int) -> str:
    """EF-I5 — *"beyond eight pupils, the number and a link, not thirty
    names"*.

    *"At the start of term the whole class has no observation, and the
    list would drown the few forgotten ones one is looking for."*
    """
    oublies = signalee["eleves"]
    debut = (f"{signalee['code']} · vue {signalee['vues']} fois au "
             f"trimestre {trimestre} : ")
    if len(oublies) > NOMS_AFFICHES:
        return (f"{debut}{len(oublies)} élèves n'ont aucune observation "
                f"cochée.")
    noms = ", ".join(f"{e['prenom']} {e['nom'].upper()}" for e in oublies)
    return f"{debut}{noms} n'ont aucune observation cochée."


feature = Feature(
    name="suivi",
    kind="logic",
    provides=[
        VerifDraft, VueSuiviEleve, panneau_verifications,
        dialogue_verification, cadres_du_jour, bandeau_des_rappels,
        ouvrir_verification, MOTIFS,
    ],
    uses=["suivi_data", "notes_data", "eleves_data", "calendrier_data",
          "grille_data", "annees"],
)
