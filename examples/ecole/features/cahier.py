"""features/cahier — page : la saisie du soir, la progression, les fiches.

EF-K1 à EF-K12, EF-L1 à EF-L3, EF-M1 à EF-M4.

Le moment d'usage, et ce qu'il décide
---------------------------------------
*« Le soir, 10 minutes : saisir les notes d'un devoir, remplir le cahier
de texte. La frappe est l'ennemi. »* Tout l'écran est construit autour de
cette phrase : la classe est déjà choisie, le chapitre aussi, la séance
suivante aussi, et le texte est déjà écrit. Ce qui reste à faire est de
LIRE et de corriger.

Les deux boutons de copie d'EF-K3
-----------------------------------
Un par champ d'École Directe — « contenu de séance » et « travail à
faire ». Deux et pas un : ce sont deux champs distincts là-bas, et une
copie unique obligerait à découper à la main dans le presse-papiers.

Les trois regards d'EF-M1, et pourquoi ils ne se confondent pas
----------------------------------------------------------------
====================  =================================================
le **chapitre**       ce qui est PRÉVU
le **cahier**         ce qui a été FAIT
la **fiche**          ce que la séance VAUT
====================  =================================================

Les fondre donnerait un seul texte qui répond mal aux trois questions.
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

#: Les deux carnets d'EF-M2, lus de part et d'autre du cours.
CARNETS: tuple[tuple[str, str, str], ...] = (
    ("preparer", "À préparer", "avant le cours"),
    ("reflexions", "Réflexions", "après le cours"),
)


class VueCahier(PageState, addressable=True):
    """La classe et la date du cahier — **et l'adresse en fait foi**.

    *« Ce qu'un lien doit retenir : la classe, la date »* (§ 8). C'est ce
    qui permet à une case de la grille d'ouvrir le cahier sur le bon jour
    (EF-B14), et c'est le second des deux chemins que le cahier promet.
    """

    classe_id: int = field(default=0, url="classe")
    jour: str = field(default="", url="date")


class SaisieCahier(PageState):
    """Le brouillon du soir : ce que la proposition a déjà rempli."""

    classe_id: int = field(default=0)
    jour: str = field(default="")
    chapitre_id: int = field(default=0)
    numero: int = field(default=1)
    titre: str = field(default="")
    contenu: str = field(default="")
    travail: str = field(default="")
    amorce: str = field(default="")


class FicheDraft(PageState):
    """Une fiche de séance en cours d'écriture (EF-M2)."""

    ouvert: bool = field(default=False)
    chapitre_id: int = field(default=0)
    titre: str = field(default="")
    resume: str = field(default="")
    carnet: str = field(default="preparer")
    note: str = field(default="")


def classe_du_moment(annee: dict) -> int:
    """EF-K2 § 1 — *« la classe DU MOMENT est déjà choisie »*.

    Elle vient de l'emploi du temps, pas d'un sélecteur : la première
    heure à venir sur les sept prochains jours. À défaut, la première
    classe de l'année — un écran vide ne répond à aucune question.
    """
    heures = prochaines_heures(annee, date.today())
    if heures:
        for ligne in classes_de(annee["id"]):
            if ligne["code"] == heures[0]["code"]:
                return ligne["id"]
    classes = classes_de(annee["id"])
    return classes[0]["id"] if classes else 0


def amorcer(vue: VueCahier, saisie: SaisieCahier) -> None:
    """Remplit le brouillon depuis la proposition (EF-K2).

    ⚠️ ``amorce`` retient POUR QUI la proposition a été faite. Sans lui,
    changer de classe garderait le texte de la précédente — et le
    professeur recopierait sur École Directe un contenu qui n'est pas
    celui de cette classe. C'est la même famille que le ``classe_id``
    des autres brouillons, et c'est la seule qui écrirait une faute
    ailleurs que dans l'app.
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
    """Vide : la mutation seule re-rend les zones ``deps=[VueCahier]``."""


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
    """EF-K10 — on reprend ce qu'une classe sœur a noté.

    **Le texte est AJUSTÉ, jamais recalculé** (EF-K9) : seule la ligne
    d'annonce du chapitre bouge, parce que la règle « le chapitre n'est
    annoncé qu'une fois » est PAR CLASSE.
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
    """EF-K3 — **deux boutons de copie, un par champ d'École Directe.**

    Deux et pas un : ce sont deux champs distincts là-bas, et une copie
    unique obligerait à découper à la main dans le presse-papiers.

    ⚠️ **Le bouton copie la valeur SERVEUR**, celle du dernier rendu.
    Copier ce que le champ contient à l'instant du clic demanderait de
    lire le DOM, et ``copy()`` prend une valeur. La conséquence est
    qu'une correction non enregistrée ne part pas dans le presse-papiers
    — c'est un finding, noté au chantier, et c'est pour ça que l'écran
    dit de consigner d'abord.
    """
    with ui.form_field(label=libelle):
        ui.textarea(value=liaison, rows=lignes, disabled=fige)
    with ui.hstack(gap="md", justify="end", align="center"):
        ui.text("Copie le texte consigné, pas la correction en cours.",
                color="muted")
        ui.button(f"Copier « {libelle.lower()} »", variant="ghost",
                  icon_left="copy", on_click=copy(valeur))


def panneau_des_soeurs(soeurs: list[dict], fige: bool) -> None:
    """EF-K10 — *« on est sur la 4e2, on cherche ce que la 4e1 a fait »*."""
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
    """EF-K8 — **la séance du jour en tête.**"""
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
    """EF-L1, EF-L2 — **un tableau, pas une liste.**

    *« Cinq classes sur un même programme dérivent l'une de l'autre sans
    qu'on s'en aperçoive, et on le découvre en juin quand il est trop
    tard. »* Le décalage se lit COLONNE PAR COLONNE : une colonne où une
    seule classe est à zéro saute aux yeux, cinq cahiers lus l'un après
    l'autre non.
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
                        # ⚠️ PAS de `truncate=True` : `ui.text` rend un
                        # `<span>`, donc en ligne — la coupure ne le
                        # borne pas dans sa piste de grille, et les
                        # titres se peignent LES UNS SUR LES AUTRES.
                        # Vu à l'écran le 2026-09-12, illisible. Un
                        # titre qui passe à la ligne coûte une rangée
                        # plus haute et se lit.
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
    """EF-M2 — **un résumé qu'on RÉÉCRIT, deux carnets où l'on AJOUTE.**

    *« Chaque note est datée et ne remplace pas la précédente : la même
    séance donnée à la 3e2 puis à la 3e9, ce sont deux observations. »*
    Les deux moitiés sont donc deux formulaires, pas un.
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
            # EF-M4 : celles qu'on n'a pas pu rattacher sont DITES, pas
            # reposées au hasard — c'est le piège n° 10, vu de l'autre
            # côté.
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
