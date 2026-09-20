"""features/reglages — page: the year, its terms, its periods.

The screen of EF-A1 to EF-A11. Three blocks, and the third is the one
that really asks something of the framework: a table where every row is
computed and **cut by working-period lines**.

What this table must say, and that is not in the columns
--------------------------------------------------------
*"A blue line across the table separates the working periods: Period 1 ·
7 weeks"* (EF-A9). The need behind the blue line is **to see where a
working period starts and how many weeks it lasts** — the line was the
original application's answer. Here it is a ``ui.divider(label=…)``,
which is literally that: a rule with a word in the middle.

And the "Cours perdus" column has **three distinct answers**, never two
(EF-A11): nothing at all for real holidays (the year is built around
them), "aucun cours ce jour-là" for an empty list — the good news — and
the list of classes when it costs. Without a week-A reference date, we
say we **do not know** rather than invent.

⚠️ **The table is not a ``ui.table``**, and it is a decision. A component
table renders homogeneous rows; here separators must be inserted BETWEEN
groups of rows, and the separating row carries computed text. It is a
grid, not a data table.
"""

from __future__ import annotations

from datetime import date
from functools import partial

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import (
    CYCLES,
    VACANCES_ZONE_B,
    jour_et_date,
    periodes_de_travail,
    semaines_touchees,
    sont_de_vraies_vacances,
)
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.calendrier_data import (
    cours_perdus,
    creer_annee,
    designer_en_cours,
    modifier_annee,
    periodes_de,
    poser_periode,
    poser_trimestre,
    supprimer_periode,
    trimestres_de,
)
from examples.ecole.features.shell import shell

PATH = "/reglages"

#: The column widths of the periods table. A single definition for the
#: header AND the rows: two strings would end up diverging by a quarter
#: of a column, which only shows on screen.
COLONNES = "grid-cols-[minmax(10rem,1.4fr)_9rem_9rem_6rem_minmax(12rem,1.6fr)]"


class ReglagesAnnee(PageState):
    """The draft of the year's four fields (EF-A1).

    ``annee_id`` is rendered by no field and arrives from the browser
    anyway: it is a declared attribute of the ``PageState``, so the base
    layer hydrates it from the POST body. It serves here to detect that
    the draft speaks of ANOTHER year than the one shown — without which
    changing year in the sidebar would leave the previous one's four
    fields.
    """

    annee_id: int = field(default=0)
    libelle: str = field(default="")
    debut: str = field(default="")
    fin: str = field(default="")
    lundi_ref: str = field(default="")


class ReglagesTrimestres(PageState):
    """The six term ends: three numbers × two cycles (EF-A3).

    Six DECLARED fields rather than a dict, and it is what the grid
    requires: it has exactly six cells, known at writing time. A declared
    field binds through ``value=``, so autoname gives it its HTML name
    and the base layer hydrates it — which an indexed dict cannot do.
    """

    annee_id: int = field(default=0)
    college_1: str = field(default="")
    college_2: str = field(default="")
    college_3: str = field(default="")
    lycee_1: str = field(default="")
    lycee_2: str = field(default="")
    lycee_3: str = field(default="")


class PeriodeDraft(PageState):
    """The period being edited, in its dialog.

    ``ouvert`` is a boolean FIELD and not an expression: a
    ``ui.dialog(open=…)`` driven by the server requires a declared field,
    otherwise the value loses its provenance and the dialog never opens
    (``livrer-une-app.md``'s silence B3).

    ``libelle_origine`` keeps the name under which the row is filed in
    the database. Without it, renaming a period would create a second one
    and leave the old: the table's key is the NAME (EF-A4).
    """

    annee_id: int = field(default=0)
    ouvert: bool = field(default=False)
    libelle_origine: str = field(default="")
    libelle: str = field(default="")
    debut: str = field(default="")
    fin: str = field(default="")


class NouvelleAnnee(PageState):
    """The year-creation draft (EF-A2)."""

    ouvert: bool = field(default=False)
    libelle: str = field(default="")
    debut: str = field(default="")
    fin: str = field(default="")


# ── Les handlers ─────────────────────────────────────────────────────

def enregistrer_annee(form: ReglagesAnnee) -> None:
    modifier_annee(int(form.annee_id), {
        "libelle": str(form.libelle).strip()[:20],
        "debut": str(form.debut),
        "fin": str(form.fin),
        "lundi_ref": str(form.lundi_ref),
    })
    ui.notification("Année enregistrée", variant="success", duration_ms=2000)


def enregistrer_trimestres(form: ReglagesTrimestres) -> None:
    """The six cells at once, empty ones included.

    An emptied cell MUST go back to the server, otherwise a date can
    never be removed. That is why saving is global and not cell by cell:
    "I entered nothing" and "I cleared it" look exactly alike in a
    partial POST.
    """
    annee_id = int(form.annee_id)
    for cycle in CYCLES:
        for numero in (1, 2, 3):
            poser_trimestre(annee_id, cycle, numero,
                            str(getattr(form, f"{cycle}_{numero}")))
    ui.notification("Trimestres enregistrés", variant="success",
                    duration_ms=2000)


def ouvrir_periode(libelle: str, debut: str, fin: str) -> None:
    """Open the dialog on a period — existing or proposed."""
    draft = PeriodeDraft()
    draft.annee_id = annee_regardee()["id"]
    draft.libelle_origine = libelle
    draft.libelle = libelle
    draft.debut = debut
    draft.fin = fin
    draft.ouvert = True


def fermer_periode(draft: PeriodeDraft) -> None:
    draft.ouvert = False


def enregistrer_periode(draft: PeriodeDraft) -> None:
    """EF-A5, en trois lignes : renommer, effacer, poser."""
    annee_id = int(draft.annee_id)
    origine = str(draft.libelle_origine)
    libelle = str(draft.libelle).strip()[:40] or origine
    if origine and libelle != origine:
        supprimer_periode(annee_id, origine)
    poser_periode(annee_id, libelle, str(draft.debut), str(draft.fin))
    draft.ouvert = False


def effacer_periode(draft: PeriodeDraft) -> None:
    supprimer_periode(int(draft.annee_id), str(draft.libelle_origine))
    draft.ouvert = False


def ouvrir_creation(brouillon: NouvelleAnnee) -> None:
    brouillon.ouvert = True


def enregistrer_nouvelle_annee(brouillon: NouvelleAnnee) -> None:
    libelle = str(brouillon.libelle).strip()[:20]
    if not (libelle and brouillon.debut and brouillon.fin):
        ui.notification("Il faut un libellé, un début et une fin.",
                        variant="warning", duration_ms=3000)
        return
    creer_annee(libelle, str(brouillon.debut), str(brouillon.fin))
    brouillon.ouvert = False
    ui.notification(f"Année {libelle} créée, en consultation.",
                    variant="success", duration_ms=3000)


def mettre_en_service(annee_id: int) -> None:
    designer_en_cours(annee_id)
    ui.notification("Année mise en service", variant="success",
                    duration_ms=2000)


# ── Block 1 · the year (EF-A1, EF-A2) ────────────────────────────────

# ⚠️ `NouvelleAnnee` is NOT here, and it is finding F12: the draft
# belongs to `creation_dialogue()`, which is a zone and already declares
# it. Carrying it here would redraw the whole block at every keystroke in
# the dialog. The `zone-listening-too-widely` rule refuses it.
@refreshable(deps=[AnneeVue, ReglagesAnnee])
def bloc_annee() -> None:
    annee = annee_regardee()
    form = ReglagesAnnee()
    if int(form.annee_id) != int(annee["id"]):
        form.annee_id = annee["id"]
        form.libelle = annee["libelle"]
        form.debut = annee["debut"]
        form.fin = annee["fin"]
        form.lundi_ref = annee["lundi_ref"] or ""

    fige = en_consultation()
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("L'année scolaire", level=2, size="lg")
        with ui.form(on_submit=enregistrer_annee), ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Libellé"):
                    ui.input(value=form.libelle, disabled=fige)
                with ui.form_field(
                    label="Lundi de référence (semaine A)",
                    hint="Vide : l'alternance A/B reste indéterminée.",
                ):
                    ui.date_picker(value=form.lundi_ref,
                                   disabled=fige)
                with ui.form_field(label="Début de l'année"):
                    ui.date_picker(value=form.debut, disabled=fige)
                with ui.form_field(label="Fin de l'année"):
                    ui.date_picker(value=form.fin, disabled=fige)
            with ui.hstack(gap="md", justify="end", wrap=True):
                if fige:
                    ui.button(
                        "Mettre cette année en service",
                        icon_left="power",
                        on_click=partial(mettre_en_service,
                                         annee["id"]),
                    )
                ui.button("Créer une année", variant="outline",
                          icon_left="calendar-plus",
                          on_click=ouvrir_creation)
                ui.button("Enregistrer", type="submit",
                          color="primary", icon_left="save",
                          disabled=fige)


@refreshable(deps=[NouvelleAnnee])
def creation_dialogue() -> None:
    brouillon = NouvelleAnnee()
    with (
        ui.dialog(open=brouillon.ouvert, title="Créer une année scolaire"),
        ui.form(on_submit=enregistrer_nouvelle_annee),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "La nouvelle année naît EN CONSULTATION. C'est un second "
            "geste qui la met en service, pour qu'aucun écran ne "
            "bascule sur une base vide par surprise.",
            color="muted",
        )
        with ui.form_field(label="Libellé", required=True):
            ui.input(value=brouillon.libelle,
                     placeholder="2027-2028")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Début", required=True):
                ui.date_picker(value=brouillon.debut)
            with ui.form_field(label="Fin", required=True):
                ui.date_picker(value=brouillon.fin)
        with ui.hstack(justify="end"):
            ui.button("Créer", type="submit", color="primary")


# ── Block 2 · the terms (EF-A3) ──────────────────────────────────────

@refreshable(deps=[AnneeVue, ReglagesTrimestres])
def bloc_trimestres() -> None:
    annee = annee_regardee()
    form = ReglagesTrimestres()
    if int(form.annee_id) != int(annee["id"]):
        connus = trimestres_de(annee["id"])
        form.annee_id = annee["id"]
        for cycle in CYCLES:
            for numero in (1, 2, 3):
                setattr(form, f"{cycle}_{numero}",
                        connus.get((cycle, numero), ""))

    fige = en_consultation()
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Les trimestres", level=2, size="lg")
        ui.text(
            "Seule la FIN se saisit : le début d'un trimestre est le "
            "lendemain du précédent. Une case vide est normale — le "
            "trimestre court alors jusqu'à la fin de l'année.",
            color="muted",
        )
        with ui.form(on_submit=enregistrer_trimestres), ui.vstack(gap="md"):
            with ui.grid(cols={"base": 1, "md": 2}, gap="lg"):
                for cycle, nom in CYCLES.items():
                    with ui.vstack(gap="sm"):
                        ui.heading(nom, level=3, size="md")
                        for numero in (1, 2, 3):
                            with ui.form_field(
                                    label=f"Fin du trimestre {numero}"):
                                ui.date_picker(
                                    value=getattr(
                                        form, f"{cycle}_{numero}"),
                                    placeholder="pas de date",
                                    disabled=fige,
                                )
            with ui.hstack(justify="end"):
                ui.button("Enregistrer", type="submit",
                          color="primary", icon_left="save",
                          disabled=fige)


# ── Block 3 · the days without class (EF-A4 … EF-A11) ────────────────

def lignes_du_tableau(annee: dict) -> list[dict]:
    """The rows to render: the periods set + the four proposed.

    EF-A4: zone B's holidays are **proposed filled in or not, without
    creating empty rows in advance**. So a proposal is a row on screen
    and nothing in the database — it only exists if it is filled in.

    EF-A6: the order is the YEAR's, and what has no date brings up the
    rear. The sort by date comes from the query (trap no. 13); what is
    decided here is only where to put the empty proposals.
    """
    posees = periodes_de(annee["id"])
    connues = {p["libelle"] for p in posees}
    lignes = [
        {"libelle": p["libelle"], "debut": p["debut"], "fin": p["fin"]}
        for p in posees
    ]
    lignes += [
        {"libelle": nom, "debut": "", "fin": ""}
        for nom in VACANCES_ZONE_B if nom not in connues
    ]
    return lignes


def cellule_cours_perdus(annee: dict, ligne: dict) -> None:
    """EF-A11's column — three answers, never two.

    The order of the tests IS the rule: we look first at whether these
    are real holidays (in which case there is nothing to say), then
    whether the alternation is computable, and only then at what it
    costs.
    """
    debut = date.fromisoformat(ligne["debut"])
    fin = date.fromisoformat(ligne["fin"])
    if sont_de_vraies_vacances(debut, fin):
        # Nothing. The year is built around them; writing "43 hours
        # lost" beside Christmas would be exact and useless noise.
        return
    perdus = cours_perdus(annee, debut, fin)
    if perdus is None:
        ui.text("alternance indéterminée", color="warning")
        return
    if not perdus:
        ui.text("aucun cours ce jour-là", color="muted")
        return
    with ui.hstack(gap="sm", wrap=True, align="center"):
        for code, heures in perdus:
            with ui.hstack(gap="none", align="baseline"):
                ui.text(code, weight="medium")
                if heures > 1:
                    # The ONLY place in the table where something
                    # really costs, hence the only one in red. An hour is
                    # not counted: "4e1" already says everything.
                    ui.text(f" ×{heures}", color="error", weight="semibold")


def ligne_periode(annee: dict, ligne: dict, fige: bool) -> None:
    posee = bool(ligne["debut"])
    with ui.grid(gap="md", classes=f"{COLONNES} items-center py-2"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon("calendar-off" if posee else "calendar-plus",
                    color="muted")
            ui.text(ligne["libelle"], weight="medium" if posee else None,
                    color=None if posee else "muted")
        # EF-A7: the weekday PRECEDES the date, and the year stays
        # shown. EF-A8: a public holiday shows BOTH its dates, identical
        # — a half-empty column reads worse than two columns always
        # filled.
        for borne in ("debut", "fin"):
            if posee:
                jour = date.fromisoformat(ligne[borne])
                with ui.vstack(gap="none"):
                    ui.text(jour_et_date(jour))
                    ui.text(str(jour.year), color="muted")
            else:
                ui.text("—", color="muted")
        if posee:
            debut = date.fromisoformat(ligne["debut"])
            fin = date.fromisoformat(ligne["fin"])
            ui.text(f"{semaines_touchees(debut, fin)} sem.", color="muted")
        else:
            ui.text("—", color="muted")
        with ui.hstack(gap="md", justify="between", align="center"):
            with ui.hstack(gap="sm", wrap=True, align="center"):
                if posee:
                    cellule_cours_perdus(annee, ligne)
            ui.icon_button(
                "pencil" if posee else "plus",
                variant="ghost",
                disabled=fige,
                aria_label=f"Modifier {ligne['libelle']}",
                on_click=partial(ouvrir_periode, ligne["libelle"],
                                 ligne["debut"], ligne["fin"]),
            )


# ``PeriodeDraft`` does not appear here: the block does not read it. It
# was there for ``periode_dialogue``, which this block called — so
# opening a period redrew the whole list.
@refreshable(deps=[AnneeVue])
def bloc_periodes() -> None:
    annee = annee_regardee()
    lignes = lignes_du_tableau(annee)
    fige = en_consultation()
    debut_annee = date.fromisoformat(annee["debut"])
    fin_annee = date.fromisoformat(annee["fin"])
    morceaux = periodes_de_travail(
        [(li["libelle"], date.fromisoformat(li["debut"]),
          date.fromisoformat(li["fin"])) for li in lignes if li["debut"]],
        debut_annee, fin_annee,
    )

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            with ui.vstack(gap="none"):
                ui.heading("Les jours sans classe", level=2, size="lg")
                ui.text(
                    "Vacances, fériés, ponts et journées banalisées : "
                    "même table, même règle. Le début et la fin sont le "
                    "premier et le DERNIER jour sans classe.",
                    color="muted",
                )
            ui.button("Ajouter un jour", variant="outline",
                      icon_left="plus", disabled=fige,
                      on_click=partial(ouvrir_periode, "", "", ""))

        with ui.grid(gap="md",
                     classes=f"{COLONNES} border-b border-text/10 pb-2"):
            for entete in ("Période", "Premier jour", "Dernier jour",
                           "Durée", "Cours perdus"):
                ui.text(entete, color="muted", weight="semibold")

        # EF-A9: the line separating the WORKING periods. It is
        # inserted before the first row whose start falls after the
        # piece's end — so between two real holidays, and never around a
        # public holiday.
        with ui.vstack(gap="none", classes="divide-y divide-text/5"):
            restants = list(morceaux)
            for ligne in lignes:
                while restants and ligne["debut"] and (
                        date.fromisoformat(ligne["debut"])
                        > restants[0][2]):
                    numero, _d, _f, semaines = restants.pop(0)
                    ui.divider(
                        label=f"Période {numero} · {semaines} semaines",
                        color="info",
                    )
                ligne_periode(annee, ligne, fige)
            for numero, _d, _f, semaines in restants:
                ui.divider(
                    label=f"Période {numero} · {semaines} semaines",
                    color="info",
                )


@refreshable(deps=[PeriodeDraft])
def periode_dialogue() -> None:
    draft = PeriodeDraft()
    with (
        ui.dialog(open=draft.ouvert, title="Jours sans classe",
                  on_close=fermer_periode),
        ui.form(on_submit=enregistrer_periode),
        ui.vstack(gap="md"),
    ):
        with ui.form_field(
            label="Libellé",
            hint="Toussaint, Noël, Février, Pâques sont proposés ; "
                 "tout le reste s'écrit librement.",
            required=True,
        ):
            ui.input(value=draft.libelle,
                     placeholder="Journée pédagogique")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(
                    label="Premier jour sans classe"):
                ui.date_picker(value=draft.debut)
            with ui.form_field(
                label="Dernier jour sans classe",
                hint="Vide : un seul jour.",
            ):
                ui.date_picker(value=draft.fin)
        with ui.hstack(justify="between", align="center"):
            ui.button("Effacer", variant="ghost", color="error",
                      icon_left="trash-2",
                      disabled=not draft.libelle_origine,
                      on_click=effacer_periode)
            ui.button("Enregistrer", type="submit", color="primary",
                      icon_left="save")


@page(PATH, layout=shell, title="Réglages")
def reglages_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Réglages", level=1, size="2xl")
        bloc_annee()
        bloc_trimestres()
        bloc_periodes()
    # Mounted by the PAGE, not by the blocks: cf. the comment on
    # ``bloc_periodes``.
    creation_dialogue()
    periode_dialogue()


feature = Feature(
    name="reglages",
    kind="page",
    provides=[reglages_page, ReglagesAnnee, ReglagesTrimestres,
              PeriodeDraft, NouvelleAnnee],
    uses=["calendrier_data", "annees", "shell"],
)
