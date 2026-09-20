"""features/classe — page: a class, its pupils, its four views.

EF-C2: *"a class shows its pupils in a photo grid, with a term selector.
One switches between four views: the pupils, the assessments, the
summary, the plan."*

⚠️ **The tabs arrive batch by batch**, and it is trap no. 14 seen close
up: a tab opening an empty panel is worse than an absent tab — it
promises something. Batch 4 delivers "Élèves"; the assessments come in
batch 5, the summary in 6, the plan in 7, and each adds its line here.

What the address keeps (EF-U1)
-------------------------------
*"The class, the term, the view."* The class is in the PATH — a resource
identifier, not a view setting. The term and the tab are in the query:
``/classe/3?t=2&vue=eleves`` opens on the same screen for whoever
receives the link.

⚠️ The tab goes through ``ui.tabs(url=…)``, which writes it into the
address on its own with no request — the panel is already mounted and it
is ``bz-show`` that flips it. The term, for its part, changes what the
SERVER computes, so it is an addressable state and it costs a round trip.
"""

from __future__ import annotations

from datetime import date
from functools import partial

from bretzel import Feature, abort, page, redirect, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import CYCLES
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.appreciations import panneau_bilan
from examples.ecole.features.eleves_data import (
    ajouter_eleve,
    classe,
    classes_de,
    eleves_de,
    eleves_emportes_par,
    faire_revenir,
    faire_sortir,
    regler_prof_principal,
    sortis_de,
    supprimer_classe,
    transferer,
)
from examples.ecole.features.evaluations import (
    dialogue_evaluation,
    panneau_evaluations,
)
from examples.ecole.features.plan import panneau_plan
from examples.ecole.features.shell import shell
from examples.ecole.features.vue_classe import (
    VueClasse,
    selecteur_trimestre,
)

#: The tabs DELIVERED. Each batch adds one — never before its panel
#: exists.
VUES: tuple[tuple[str, str, str], ...] = (
    ("eleves", "Élèves", "users"),
    ("evaluations", "Évaluations", "clipboard-list"),
    ("bilan", "Bilan", "chart-column"),
    ("plan", "Plan", "layout-dashboard"),
)


class EnteteClasse(PageState):
    """The header's draft: the form tutor (EF-C6)."""

    classe_id: int = field(default=0)
    prof_principal: str = field(default="")


class MouvementDraft(PageState):
    """A pupil movement: add, leave, return, transfer.

    A single draft for the four gestures, because it is a single dialog
    whose body changes: all four share the date, and three share the
    pupil.
    """

    ouvert: bool = field(default=False)
    geste: str = field(default="ajouter")
    classe_id: int = field(default=0)
    eleve_id: int = field(default=0)
    nom: str = field(default="")
    prenom: str = field(default="")
    vers: str = field(default="")
    jour: str = field(default="")


class SuppressionDraft(PageState):
    """EF-C8's EXPLICIT confirmation, and what it costs."""

    ouvert: bool = field(default=False)
    classe_id: int = field(default=0)
    emportes: int = field(default=0)


# ── Les handlers ─────────────────────────────────────────────────────

def enregistrer_entete(form: EnteteClasse) -> None:
    regler_prof_principal(int(form.classe_id), annee_regardee()["id"],
                          str(form.prof_principal))
    ui.notification("Professeur principal enregistré", variant="success",
                    duration_ms=2000)


def ouvrir_mouvement(geste: str, classe_id: int, eleve_id: int,
                     nom: str) -> None:
    draft = MouvementDraft()
    draft.geste = geste
    draft.classe_id = classe_id
    draft.eleve_id = eleve_id
    draft.nom = nom
    draft.prenom = ""
    draft.vers = ""
    draft.jour = date.today().isoformat()
    draft.ouvert = True


def fermer_mouvement(draft: MouvementDraft) -> None:
    draft.ouvert = False


def enregistrer_mouvement(draft: MouvementDraft) -> None:
    """EF-C5's four gestures, in the only place that knows them."""
    annee_id = annee_regardee()["id"]
    classe_id = int(draft.classe_id)
    geste = str(draft.geste)
    jour = str(draft.jour) or date.today().isoformat()

    if geste == "ajouter":
        nom, prenom = str(draft.nom).strip(), str(draft.prenom).strip()
        if not (nom and prenom):
            ui.notification("Il faut un nom ET un prénom — les deux restent "
                            "distincts (EF-C7).", variant="warning",
                            duration_ms=3000)
            return
        ajouter_eleve(classe_id, annee_id, nom, prenom, jour)
    elif geste == "sortir":
        faire_sortir(int(draft.eleve_id), classe_id, annee_id, jour)
    elif geste == "revenir":
        faire_revenir(int(draft.eleve_id), classe_id, annee_id, jour)
    elif geste == "transferer":
        vers = str(draft.vers)
        if not vers:
            ui.notification("Choisissez la classe d'arrivée.",
                            variant="warning", duration_ms=3000)
            return
        transferer(int(draft.eleve_id), classe_id, int(vers), annee_id, jour)
    draft.ouvert = False


def ouvrir_suppression(classe_id: int) -> None:
    draft = SuppressionDraft()
    draft.classe_id = classe_id
    draft.emportes = eleves_emportes_par(classe_id)
    draft.ouvert = True


def fermer_suppression(draft: SuppressionDraft) -> None:
    draft.ouvert = False


def confirmer_suppression(draft: SuppressionDraft) -> None:
    supprimer_classe(int(draft.classe_id), annee_regardee()["id"])
    draft.ouvert = False
    redirect("/classes")


# ── Le rendu ─────────────────────────────────────────────────────────

def lien_vers_le_plan() -> None:
    """The Plan tab: the plan itself, and the path to its screen.

    The panel is ``features/plan.py``'s — the SAME, not a copy: two
    renderings of a seating plan would diverge, and the one not being
    looked at would be the false one.
    """
    vue = VueClasse()
    with ui.vstack(gap="md"):
        ui.link(
            label="Ouvrir le plan en grand (et le figer)",
            href=f"/plan/{int(vue.classe_id)}",
            variant="underline",
        )
        panneau_plan()


def vignette(eleve_ligne: dict, classe_id: int, fige: bool) -> None:
    """A pupil in the grid: their face, their name, their particularities.

    The demonstration set carries **coloured initials** and not faces
    (§ 12 of the specification): it is soberer, and it removes any
    ambiguity about where the images come from. ``ui.avatar`` derives
    them from the name on its own — computing them here would be
    duplicated work.
    """
    with (
        ui.card(padding="sm", href=f"/eleve/{eleve_ligne['id']}"),
        ui.vstack(gap="sm", align="center"),
    ):
        ui.avatar(name=f"{eleve_ligne['prenom']} {eleve_ligne['nom']}",
                  size="xl", shape="circle")
        with ui.vstack(gap="none", align="center"):
            ui.text(eleve_ligne["nom"].upper(), weight="semibold",
                    truncate=True)
            ui.text(eleve_ligne["prenom"], color="muted", truncate=True)
        with ui.hstack(gap="sm", justify="center", wrap=True):
            if eleve_ligne["amenagement"]:
                ui.badge(label=eleve_ligne["amenagement"], color="info",
                         variant="soft", size="xl")
            if eleve_ligne["vue_fragile"]:
                ui.icon("eye", color="warning", tooltip="Vue fragile")
            if eleve_ligne["gaucher"]:
                ui.icon("hand", color="muted", tooltip="Gaucher")
            if eleve_ligne["demi_groupe"]:
                ui.badge(label=f"TP {eleve_ligne['demi_groupe']}",
                         color="secondary", variant="outline", size="xl")


@refreshable(deps=[AnneeVue, VueClasse, MouvementDraft, EnteteClasse])
def panneau_eleves() -> None:
    classe_id = int(VueClasse().classe_id)
    fige = en_consultation()
    liste = eleves_de(classe_id)
    partis = sortis_de(classe_id)

    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.text(f"{len(liste)} élèves en cours d'inscription",
                    color="muted")
            # EF-C10: the movement is only OFFERED on the current
            # year. The prohibition comes from RT-1 and lives in the
            # guard; here it is about not offering a button that will
            # refuse.
            if not fige:
                ui.button("Ajouter un élève", icon_left="user-plus",
                          variant="outline",
                          on_click=partial(ouvrir_mouvement, "ajouter",
                                           classe_id, 0, ""))
        with ui.grid(min_col="12rem", gap="md"):
            for ligne in ui.each(liste, key="id"):
                vignette(ligne, classe_id, fige)

        if partis:
            ui.divider(label=f"{len(partis)} élève(s) sorti(s)")
            with ui.vstack(gap="sm"):
                for ligne in ui.each(partis, key="id"):
                    with ui.hstack(gap="md", align="center", wrap=True):
                        ui.avatar(
                            name=f"{ligne['prenom']} {ligne['nom']}",
                            size="lg", shape="circle", color="muted")
                        ui.text(f"{ligne['nom'].upper()} {ligne['prenom']}")
                        ui.text(f"sorti le {ligne['fin']}", color="muted")
                        if not fige:
                            ui.button(
                                "Le faire revenir", variant="ghost",
                                icon_left="undo-2",
                                on_click=partial(
                                    ouvrir_mouvement, "revenir", classe_id,
                                    ligne["id"], ligne["nom"]))


@refreshable(deps=[AnneeVue, VueClasse, EnteteClasse])
def entete() -> None:
    classe_id = int(VueClasse().classe_id)
    donnees = classe(classe_id)
    if donnees is None:
        return
    form = EnteteClasse()
    if int(form.classe_id) != classe_id:
        form.classe_id = classe_id
        form.prof_principal = donnees["prof_principal"]
    fige = en_consultation()

    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            with ui.vstack(gap="none"):
                ui.heading(donnees["code"], level=1, size="2xl")
                ui.text(f"{donnees['libelle']} · {CYCLES[donnees['cycle']]}",
                        color="muted")
            if not fige:
                ui.button("Supprimer cette classe", variant="ghost",
                          color="error", icon_left="trash-2",
                          on_click=partial(ouvrir_suppression, classe_id))
        with (
            ui.form(on_submit=enregistrer_entete),
            ui.hstack(gap="md", align="end", wrap=True),
        ):
            with ui.form_field(label="Professeur principal"):
                ui.input(value=form.prof_principal, disabled=fige,
                         placeholder="Mme Ferrandin")
            if donnees["prof_principal"]:
                # EF-C6: their name opens a mail link. The address is
                # derived from the name for want of a dedicated column —
                # it is what the original application did, and it works
                # as long as the school follows its convention.
                ui.link(
                    label="Écrire",
                    href=courriel_de(donnees["prof_principal"]),
                    variant="underline",
                )
            ui.button("Enregistrer", type="submit", disabled=fige,
                      icon_left="save")


def courriel_de(nom: str) -> str:
    """``Mme Ferrandin`` → ``mailto:ferrandin@etablissement.fr``."""
    morceaux = [m for m in nom.replace(".", " ").split()
                if m.lower() not in ("mme", "m", "mr", "monsieur", "madame")]
    return "mailto:" + ("".join(morceaux).lower() or "contact") \
        + "@etablissement.fr"


@refreshable(deps=[MouvementDraft])
def dialogue_mouvement() -> None:
    draft = MouvementDraft()
    geste = str(draft.geste)
    titres = {
        "ajouter": "Ajouter un élève",
        "sortir": f"Faire sortir {draft.nom}",
        "revenir": f"Faire revenir {draft.nom}",
        "transferer": f"Transférer {draft.nom}",
    }
    with (
        ui.dialog(open=draft.ouvert, title=titres.get(geste, "Mouvement"),
                  on_close=fermer_mouvement),
        ui.form(on_submit=enregistrer_mouvement),
        ui.vstack(gap="md"),
    ):
        if geste == "ajouter":
            ui.text(
                "Le nom et le prénom restent DISTINCTS : un élève qui "
                "s'appelle LEA de son nom ne doit pas se confondre avec une "
                "Léa de prénom.",
                color="muted",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Nom", required=True):
                    ui.input(value=draft.nom)
                with ui.form_field(label="Prénom", required=True):
                    ui.input(value=draft.prenom)
        elif geste == "sortir":
            ui.text(
                "Rien ne s'efface : l'inscription reçoit une date de fin. "
                "L'élève quitte les listes, ses notes restent, et on peut "
                "le réinscrire.",
                color="muted",
            )
        elif geste == "transferer":
            ui.text(
                "Un transfert est une sortie PLUS une entrée : le parcours "
                "garde les deux classes et leurs dates.",
                color="muted",
            )
            with ui.form_field(label="Classe d'arrivée", required=True):
                ui.select(
                    value=draft.vers,
                    options=[
                        (str(c["id"]), f"{c['code']} — {c['libelle']}")
                        for c in classes_de(annee_regardee()["id"])
                        if c["id"] != int(draft.classe_id)
                    ],
                )
        with ui.form_field(label="À partir du"):
            ui.date_picker(value=draft.jour)
        with ui.hstack(justify="end"):
            ui.button("Enregistrer", type="submit", color="primary")


@refreshable(deps=[SuppressionDraft])
def dialogue_suppression() -> None:
    draft = SuppressionDraft()
    emportes = int(draft.emportes)
    with (
        ui.dialog(open=draft.ouvert, title="Supprimer cette classe",
                  on_close=fermer_suppression),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "Les notes, les appréciations, les plans et le cahier de texte "
            "de cette classe seront supprimés avec elle.",
        )
        # EF-C8: a confirmation that does not say what it costs is not
        # one. RT-2: the pupils belonging ONLY to it leave too —
        # otherwise they would stay in the database with no class,
        # invisible.
        ui.banner(
            message=(f"{emportes} élève(s) n'appartiennent qu'à cette "
                     f"classe et seront supprimés."
                     if emportes else
                     "Aucun élève ne sera supprimé : tous sont inscrits "
                     "ailleurs."),
            color="error" if emportes else "info",
            icon="triangle-alert" if emportes else "info",
                    size="lg",
        )
        with ui.hstack(gap="md", justify="end"):
            ui.button("Renoncer", variant="ghost",
                      on_click=fermer_suppression)
            ui.button("Supprimer définitivement", color="error",
                      icon_left="trash-2", on_click=confirmer_suppression)


@page("/classe/{classe_id}", layout=shell, title="Classe")
def classe_page(classe_id: int) -> None:
    donnees = classe(int(classe_id))
    if donnees is None:
        abort(404)
    # The page SEEDS the identity; the zones READ it. A ``@refreshable``
    # zone re-renders outside the routing: it has no path parameter at
    # hand.
    vue = VueClasse()
    if int(vue.classe_id) != int(classe_id):
        vue.classe_id = int(classe_id)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            ui.breadcrumb_item(label=donnees["code"])
        entete()
        selecteur_trimestre()
        with ui.tabs(value="eleves", url="vue"):
            for valeur, libelle, icone in VUES:
                ui.tab(valeur, label=libelle, icon=icone)
            with ui.tab_panel(tab="eleves"):
                panneau_eleves()
            with ui.tab_panel(tab="evaluations"):
                panneau_evaluations()
            with ui.tab_panel(tab="bilan"):
                panneau_bilan()
            with ui.tab_panel(tab="plan"):
                # EF-G14: the "Figer" button lives in the plan screen's
                # HEADER, not in the plan's bar. Here we send to that
                # screen rather than replay it in miniature in a tab.
                lien_vers_le_plan()
    dialogue_mouvement()
    dialogue_suppression()
    dialogue_evaluation()


feature = Feature(
    name="classe",
    kind="page",
    provides=[classe_page, EnteteClasse, MouvementDraft,
              SuppressionDraft, ouvrir_mouvement, courriel_de],
    uses=["eleves_data", "annees", "shell", "vue_classe",
          "evaluations", "appreciations", "plan"],
)
