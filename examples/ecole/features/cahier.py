"""features/cahier — page: the evening entry, the progression, the sheets.

EF-K1 to EF-K12, EF-L1 to EF-L3, EF-M1 to EF-M4.

The moment of use, and what it decides
----------------------------------------
*"In the evening, 10 minutes: entering a test's marks, filling in the
lesson log. Typing is the enemy."* The whole screen is built around that
sentence: the class is already chosen, so is the chapter, so is the next
session, and the text is already written. What is left to do is to READ
and correct.

EF-K3's two copy buttons
--------------------------
One per École Directe field — "session content" and "homework". Two and
not one: they are two distinct fields over there, and a single copy would
force cutting by hand in the clipboard.

EF-M1's three viewpoints, and why they do not merge
-----------------------------------------------------
====================  =================================================
the **chapter**       what is PLANNED
the **log**           what was DONE
the **sheet**         what the session is WORTH
====================  =================================================

Merging them would give a single text answering all three badly.
"""

from __future__ import annotations

from datetime import date
from functools import partial

from bretzel import Feature, copy, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import jour_et_date
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.cahier_data import (
    CahierRev,
    ajouter_note,
    ce_qua_note_une_soeur,
    chapitre_deja_annonce,
    chapitres_du_niveau,
    ecrire_resume,
    entrees_de,
    fiche_seance,
    fiches_orphelines,
    marquer_reportee,
    niveaux_enseignes,
    poser_entree,
    prochaines_heures,
    progression,
    proposition,
    reprendre,
)
from examples.ecole.features.eleves_data import classe, classes_de
from examples.ecole.features.shell import shell

PATH = "/cahier"

#: EF-M2's two notebooks, read on either side of the lesson.
CARNETS: tuple[tuple[str, str, str], ...] = (
    ("preparer", "À préparer", "avant le cours"),
    ("reflexions", "Réflexions", "après le cours"),
)


class VueCahier(PageState, addressable=True):
    """The class and the log's date — **and the address is
    authoritative**.

    *"What a link must keep: the class, the date"* (§ 8). It is what lets
    a grid cell open the log on the right day (EF-B14), and it is the
    second of the two paths the specification promises.
    """

    classe_id: int = field(default=0, url="classe")
    jour: str = field(default="", url="date")


class SaisieCahier(PageState):
    """The evening draft: what the proposal has already filled in."""

    classe_id: int = field(default=0)
    jour: str = field(default="")
    chapitre_id: int = field(default=0)
    numero: int = field(default=1)
    titre: str = field(default="")
    contenu: str = field(default="")
    travail: str = field(default="")
    amorce: str = field(default="")


class FicheDraft(PageState):
    """A session sheet being written (EF-M2)."""

    ouvert: bool = field(default=False)
    chapitre_id: int = field(default=0)
    titre: str = field(default="")
    resume: str = field(default="")
    carnet: str = field(default="preparer")
    note: str = field(default="")


def classe_du_moment(annee: dict) -> int:
    """EF-K2 § 1 — *"the class OF THE MOMENT is already chosen"*.

    It comes from the timetable, not from a selector: the first hour
    coming up over the next seven days. Failing that, the year's first
    class — an empty screen answers no question.
    """
    heures = prochaines_heures(annee, date.today())
    if heures:
        for ligne in classes_de(annee["id"]):
            if ligne["code"] == heures[0]["code"]:
                return ligne["id"]
    classes = classes_de(annee["id"])
    return classes[0]["id"] if classes else 0


def amorcer(vue: VueCahier, saisie: SaisieCahier) -> None:
    """Fill the draft from the proposal (EF-K2).

    ⚠️ ``amorce`` keeps WHO the proposal was made for. Without it,
    changing class would keep the previous one's text — and the teacher
    would copy onto École Directe a content that is not this class's. It
    is the same family as the other drafts' ``classe_id``, and it is the
    only one that would write a mistake outside the app.
    """
    annee = annee_regardee()
    classe_id = int(vue.classe_id) or classe_du_moment(annee)
    jour = str(vue.jour) or date.today().isoformat()
    empreinte = f"{classe_id}/{jour}"
    if str(saisie.amorce) == empreinte:
        return
    donnees = classe(classe_id)
    if donnees is None:
        return
    propose = proposition(classe_id, donnees["niveau"])
    saisie.classe_id = classe_id
    saisie.jour = jour
    saisie.chapitre_id = propose["chapitre_id"] or 0
    saisie.numero = propose["numero"]
    saisie.titre = propose["titre"]
    saisie.contenu = propose["contenu"]
    saisie.travail = propose["travail"]
    saisie.amorce = empreinte


# ── Les handlers ─────────────────────────────────────────────────────

def changer_classe(vue: VueCahier) -> None:
    """Empty: the mutation alone re-renders the ``deps=[VueCahier]``
    zones."""


def enregistrer(saisie: SaisieCahier) -> None:
    annee = annee_regardee()
    poser_entree(int(saisie.classe_id), annee["id"], {
        "date": str(saisie.jour) or date.today().isoformat(),
        "chapitre_id": int(saisie.chapitre_id) or None,
        "numero": int(saisie.numero),
        "titre": str(saisie.titre),
        "contenu": str(saisie.contenu),
        "travail": str(saisie.travail),
    })
    saisie.amorce = ""       # la prochaine séance se reproposera
    ui.notification("Séance consignée", variant="success", duration_ms=2000)


def reporter(entree_id: int) -> None:
    marquer_reportee(entree_id, annee_regardee()["id"])


def reprendre_de_la_soeur(contenu: str, travail: str) -> None:
    """EF-K10 — one picks up what a sister class recorded.

    **The text is ADJUSTED, never recomputed** (EF-K9): only the
    chapter-announcement line moves, because the rule "the chapter is
    announced only once" is PER CLASS.
    """
    saisie = SaisieCahier()
    donnees = classe(int(saisie.classe_id))
    chapitres = {c["id"]: c["titre"] for c in
                 chapitres_du_niveau(donnees["niveau"])} if donnees else {}
    titre_chapitre = chapitres.get(int(saisie.chapitre_id), "")
    annoncer = not chapitre_deja_annonce(int(saisie.classe_id),
                                         int(saisie.chapitre_id))
    saisie.contenu = reprendre(contenu, titre_chapitre, annoncer)
    saisie.travail = travail


def ouvrir_fiche(chapitre_id: int, titre: str) -> None:
    draft = FicheDraft()
    existante = fiche_seance(chapitre_id, titre)
    draft.chapitre_id = chapitre_id
    draft.titre = titre
    draft.resume = (existante or {}).get("resume", "")
    draft.carnet = "preparer"
    draft.note = ""
    draft.ouvert = True


def fermer_fiche(draft: FicheDraft) -> None:
    draft.ouvert = False


def enregistrer_resume(draft: FicheDraft) -> None:
    ecrire_resume(int(draft.chapitre_id), str(draft.titre),
                  annee_regardee()["id"], str(draft.resume))
    ui.notification("Résumé enregistré", variant="success", duration_ms=2000)


def ajouter_une_note(draft: FicheDraft) -> None:
    texte = str(draft.note).strip()
    if not texte:
        return
    ajouter_note(int(draft.chapitre_id), str(draft.titre),
                 annee_regardee()["id"], str(draft.carnet), texte)
    draft.note = ""


# ── Le rendu ─────────────────────────────────────────────────────────

@refreshable(deps=[AnneeVue, VueCahier, SaisieCahier, CahierRev])
def formulaire_du_soir() -> None:
    annee = annee_regardee()
    vue = VueCahier()
    saisie = SaisieCahier()
    amorcer(vue, saisie)
    donnees = classe(int(saisie.classe_id))
    if donnees is None:
        ui.empty_state(title="Aucune classe sur cette année", icon="school")
        return
    fige = en_consultation()
    soeurs = ce_qua_note_une_soeur(
        int(saisie.classe_id), donnees["niveau"],
        int(saisie.chapitre_id), str(saisie.titre))

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.heading("Ce qu'on a fait", level=2, size="lg")
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.text("Classe", color="muted")
                ui.select(
                    value=vue.classe_id,
                    options=[(c["id"], c["code"])
                             for c in classes_de(annee["id"])],
                    on_change=changer_classe,
                )
        ui.text(
            "La classe du moment, le chapitre en cours et la séance "
            "suivante sont déjà choisis d'après l'emploi du temps. Le "
            "chapitre n'est annoncé qu'une fois par classe — répété à "
            "chaque séance, il noierait le titre du jour sur École Directe.",
            color="muted",
        )
        if soeurs:
            panneau_des_soeurs(soeurs, fige)

        with ui.form(on_submit=enregistrer), ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.form_field(label="Date"):
                    ui.date_picker(value=saisie.jour, disabled=fige)
                with ui.form_field(label="Chapitre"):
                    ui.select(
                        value=saisie.chapitre_id,
                        options=[(c["id"], c["titre"]) for c in
                                 chapitres_du_niveau(donnees["niveau"])],
                        disabled=fige,
                    )
                with ui.form_field(label="Séance n°"):
                    ui.number_input(value=saisie.numero, min=1, max=30,
                                    step=1, disabled=fige)
            with ui.form_field(label="Titre de la séance"):
                ui.input(value=saisie.titre, disabled=fige)
            champ_copiable("Contenu de séance", saisie.contenu,
                           str(saisie.contenu), fige, 4)
            champ_copiable("Travail à faire", saisie.travail,
                           str(saisie.travail), fige, 2)
            with ui.hstack(gap="md", justify="end", wrap=True):
                ui.button(
                    "Fiche de cette séance", variant="ghost",
                    icon_left="notebook-pen", disabled=fige,
                    on_click=partial(ouvrir_fiche, int(saisie.chapitre_id),
                                     str(saisie.titre)))
                ui.button("Consigner", type="submit", color="primary",
                          icon_left="save", disabled=fige)


def champ_copiable(libelle: str, liaison, valeur: str, fige: bool,
                   lignes: int) -> None:
    """EF-K3 — **two copy buttons, one per École Directe field.**

    Two and not one: they are two distinct fields over there, and a
    single copy would force cutting by hand in the clipboard.

    ⚠️ **The button copies the SERVER value**, that of the last render.
    Copying what the field contains at the instant of the click would
    require reading the DOM, and ``copy()`` takes a value. The
    consequence is that an unsaved correction does not go into the
    clipboard — it is a finding, noted in the work, and it is why the
    screen says to record first.
    """
    with ui.form_field(label=libelle):
        ui.textarea(value=liaison, rows=lignes, disabled=fige)
    with ui.hstack(gap="md", justify="end", align="center"):
        ui.text("Copie le texte consigné, pas la correction en cours.",
                color="muted")
        ui.button(f"Copier « {libelle.lower()} »", variant="ghost",
                  icon_left="copy", on_click=copy(valeur))


def panneau_des_soeurs(soeurs: list[dict], fige: bool) -> None:
    """EF-K10 — *"we are on 4e2, we look for what 4e1 did"*."""
    with ui.card(padding="md", color="secondary"), ui.vstack(gap="sm"):
        ui.heading("Une classe sœur a déjà noté cette séance", level=3,
                   size="md")
        for soeur in ui.each(soeurs, key="id"):
            with ui.vstack(gap="sm"):
                ui.text(soeur["code"], weight="semibold")
                ui.text(soeur["contenu"], color="muted")
                ui.button(
                    "Reprendre ce texte", variant="outline",
                    icon_left="copy-plus", disabled=fige,
                    on_click=partial(reprendre_de_la_soeur, soeur["contenu"],
                                     soeur["travail"]))


@refreshable(deps=[AnneeVue, VueCahier, CahierRev])
def liste_des_entrees() -> None:
    """EF-K8 — **the day's session at the head.**"""
    saisie = SaisieCahier()
    classe_id = int(saisie.classe_id)
    if not classe_id:
        return
    lignes = entrees_de(classe_id)
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="baseline", wrap=True):
            ui.heading("Déjà consigné", level=2, size="lg")
            ui.text(f"{len(lignes)} séance(s)", color="muted")
        for ligne in ui.each(lignes[:20], key="id"):
            with ui.hstack(gap="md", align="start", justify="between",
                           wrap=True):
                with ui.vstack(gap="none"):
                    ui.text(f"{jour_et_date(date.fromisoformat(ligne['date']))}"
                            f" · séance {ligne['seance_numero']} : "
                            f"{ligne['seance_titre']}", weight="medium")
                    ui.text(ligne["contenu"], color="muted")
                with ui.hstack(gap="sm", align="center"):
                    if ligne["reporte_le"]:
                        ui.badge(label=f"reporté le {ligne['reporte_le']}",
                                 color="success", variant="soft", size="xl")
                    elif not en_consultation():
                        ui.button("Marquer reportée", variant="ghost",
                                  on_click=partial(reporter, ligne["id"]))


@refreshable(deps=[AnneeVue, CahierRev])
def tableau_de_progression() -> None:
    """EF-L1, EF-L2 — **a table, not a list.**

    *"Five classes on the same syllabus drift apart without anybody
    noticing, and one discovers it in June when it is too late."* The gap
    reads COLUMN BY COLUMN: a column where a single class is at zero
    leaps out, five logs read one after the other do not.
    """
    annee = annee_regardee()
    with ui.vstack(gap="lg"):
        for niveau in niveaux_enseignes(annee["id"]):
            table = progression(annee["id"], niveau)
            if not table["chapitres"] or len(table["classes"]) < 2:
                continue
            with ui.card(padding="md"), ui.vstack(gap="sm"):
                ui.heading(f"Niveau {niveau}", level=3, size="md")
                with ui.grid(
                    gap="sm",
                    classes="grid-cols-[6rem_repeat(auto-fit,minmax(7rem,1fr))]",
                ):
                    ui.text("", color="muted")
                    for chapitre in table["chapitres"]:
                        # ⚠️ NO `truncate=True`: `ui.text` renders a
                        # `<span>`, hence inline — the cut does not bound
                        # it in its grid track, and the titles paint ON
                        # TOP OF each other. Seen on screen on
                        # 2026-09-12, unreadable. A title that wraps
                        # costs a taller row and reads.
                        ui.text(chapitre["titre"], color="muted",
                                size="sm", tooltip=chapitre["titre"])
                    for ligne in table["classes"]:
                        ui.text(ligne["code"], weight="semibold")
                        for chapitre in table["chapitres"]:
                            faites = table["faites"].get(
                                (ligne["id"], chapitre["id"]), 0)
                            total = table["totaux"].get(chapitre["id"], 0)
                            ui.text(
                                f"{faites}/{total}" if total else "—",
                                color=("success" if total and faites >= total
                                       else "warning" if faites
                                       else "muted"),
                            )


@refreshable(deps=[FicheDraft, CahierRev])
def dialogue_fiche() -> None:
    """EF-M2 — **a summary one REWRITES, two notebooks one ADDS to.**

    *"Every note is dated and does not replace the previous one: the same
    session given to 3e2 then to 3e9 makes two observations."* So the two
    halves are two forms, not one.
    """
    draft = FicheDraft()
    existante = fiche_seance(int(draft.chapitre_id), str(draft.titre))
    orphelines = fiches_orphelines(int(draft.chapitre_id))
    with (
        ui.dialog(open=draft.ouvert, title=f"Fiche · {draft.titre}",
                  on_close=fermer_fiche, width="lg"),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "Trois regards distincts : le chapitre dit ce qui est prévu, le "
            "cahier ce qui a été fait, la fiche ce que la séance vaut.",
            color="muted",
        )
        if orphelines:
            # EF-M4: those that could not be reattached are SAID, not
            # put back at random — it is trap no. 10, seen from the other
            # side.
            ui.banner(
                message=f"{len(orphelines)} fiche(s) de ce chapitre ne "
                        f"correspondent à aucune séance : "
                        f"{', '.join(orphelines[:3])}. Une séance a dû être "
                        f"renommée.",
                icon="unlink", color="warning", size="lg",
            )
        with ui.form(on_submit=enregistrer_resume), ui.vstack(gap="sm"):
            with ui.form_field(label="Résumé",
                               hint="Il se corrige : c'est la moitié qu'on "
                                    "réécrit."):
                ui.textarea(value=draft.resume, rows=3)
            with ui.hstack(justify="end"):
                ui.button("Enregistrer le résumé", type="submit",
                          variant="outline")
        ui.divider(label="Les deux carnets")
        for carnet, libelle, quand in CARNETS:
            notes = [n for n in (existante or {}).get("notes", [])
                     if n["carnet"] == carnet]
            with ui.vstack(gap="sm"):
                ui.text(f"{libelle} ({quand})", weight="semibold")
                for note in ui.each(notes, key="id"):
                    ui.text(f"{note['cree_le']} — {note['texte']}",
                            color="muted")
        with ui.form(on_submit=ajouter_une_note), ui.vstack(gap="sm"):
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.form_field(label="Carnet"):
                    ui.select(value=draft.carnet,
                              options=[(c, li) for c, li, _q in CARNETS])
                with ui.form_field(label="Une observation de plus",
                                   hint="Elle s'ajoute, elle ne remplace "
                                        "rien."):
                    ui.input(value=draft.note)
            with ui.hstack(justify="end"):
                ui.button("Ajouter", type="submit", color="primary")


@page(PATH, layout=shell, title="Cahier de texte")
def cahier_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Cahier de texte", level=1, size="2xl")
        formulaire_du_soir()
        liste_des_entrees()
        ui.divider(label="Progression par niveau")
        tableau_de_progression()
    dialogue_fiche()


feature = Feature(
    name="cahier",
    kind="page",
    provides=[cahier_page, VueCahier, SaisieCahier, FicheDraft],
    uses=["cahier_data", "eleves_data", "annees", "shell"],
)
