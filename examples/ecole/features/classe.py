"""features/classe — page : une classe, ses élèves, ses quatre vues.

EF-C2 : *« une classe montre ses élèves en grille de photos, avec un
sélecteur de trimestre. On bascule entre quatre vues : les élèves, les
évaluations, le bilan, le plan. »*

⚠️ **Les onglets arrivent lot par lot**, et c'est le piège n° 14 vu de
près : un onglet qui ouvre un panneau vide est pire qu'un onglet absent —
il promet quelque chose. Le lot 4 livre « Élèves » ; les évaluations
viennent au lot 5, le bilan au lot 6, le plan au lot 7, et chacun ajoute
sa ligne ici.

Ce que l'adresse retient (EF-U1)
---------------------------------
*« La classe, le trimestre, la vue. »* La classe est dans le CHEMIN — un
identifiant de ressource, pas un réglage de vue. Le trimestre et l'onglet
sont dans la query : ``/classe/3?t=2&vue=eleves`` s'ouvre sur le même
écran chez qui reçoit le lien.

⚠️ L'onglet passe par ``ui.tabs(url=…)``, qui l'écrit tout seul dans
l'adresse sans aucune requête — le panneau est déjà monté et c'est
``bz-show`` qui bascule. Le trimestre, lui, change ce que le SERVEUR
calcule, donc il est un état adressable et il coûte un aller-retour.
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

#: Les onglets LIVRÉS. Chaque lot en ajoute un — jamais avant que son
#: panneau existe.
VUES: tuple[tuple[str, str, str], ...] = (
    ("eleves", "Élèves", "users"),
    ("evaluations", "Évaluations", "clipboard-list"),
    ("bilan", "Bilan", "chart-column"),
    ("plan", "Plan", "layout-dashboard"),
)


class EnteteClasse(PageState):
    """Le brouillon de l'en-tête : le professeur principal (EF-C6)."""

    classe_id: int = field(default=0)
    prof_principal: str = field(default="")


class MouvementDraft(PageState):
    """Un mouvement d'élève : ajouter, sortir, revenir, transférer.

    Un seul brouillon pour les quatre gestes, parce que c'est une seule
    boîte de dialogue dont le corps change : les quatre partagent la
    date, et trois partagent l'élève.
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
    """La confirmation EXPLICITE d'EF-C8, et ce qu'elle coûte."""

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
    """Les quatre gestes d'EF-C5, dans le seul endroit qui les connaît."""
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
    """L'onglet Plan : le plan lui-même, et le chemin vers son écran.

    Le panneau est celui de ``features/plan.py`` — le MÊME, pas une
    copie : deux rendus d'un plan de classe divergeraient, et celui
    qu'on ne regarde pas serait le faux.
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
    """Un élève dans la grille : son visage, son nom, ses particularités.

    Le jeu de démonstration porte des **initiales colorées** et pas des
    visages (§ 12 du cahier) : c'est plus sobre, et ça retire toute
    ambiguïté sur l'origine des images. ``ui.avatar`` les dérive du nom
    tout seul — les calculer ici serait du travail en double.
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
            # EF-C10 : le mouvement ne se PROPOSE que sur l'année en
            # cours. L'interdit vient de RT-1 et vit dans la garde ; ici
            # il s'agit de ne pas offrir un bouton qui refusera.
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
                # EF-C6 : son nom ouvre un lien de courrier. L'adresse
                # est dérivée du nom faute de colonne dédiée — c'est
                # ce que faisait l'application d'origine, et ça marche
                # tant que l'établissement suit sa convention.
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
        # EF-C8 : une confirmation qui ne dit pas ce qu'elle coûte n'en
        # est pas une. RT-2 : les élèves qui n'appartiennent QU'À elle
        # partent aussi — sinon ils resteraient en base sans classe,
        # invisibles.
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
    # La page SÈME l'identité ; les zones la LISENT. Une zone
    # ``@refreshable`` se re-rend hors du routage : elle n'a aucun
    # paramètre de chemin sous la main.
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
                # EF-G14 : le bouton « Figer » vit dans l'EN-TÊTE de
                # l'écran de plan, pas dans la barre du plan. Ici, on
                # renvoie vers cet écran plutôt que de le rejouer en
                # miniature dans un onglet.
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
