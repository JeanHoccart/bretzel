"""features/reglages — page : l'année, ses trimestres, ses périodes.

L'écran d'EF-A1 à EF-A11. Trois blocs, et le troisième est celui qui
demande vraiment quelque chose au framework : un tableau dont chaque
ligne est calculée et **coupé par des lignes de période de travail**.

Ce que ce tableau doit dire, et qui n'est pas dans les colonnes
---------------------------------------------------------------
*« Une ligne bleue en travers du tableau sépare les périodes de travail :
Période 1 · 7 semaines »* (EF-A9). Le besoin derrière la ligne bleue est
**qu'on voie où une période de travail commence et combien de semaines
elle dure** — la ligne était la réponse de l'application d'origine. Ici
c'est un ``ui.divider(label=…)``, qui est littéralement ça : un trait
avec un mot au milieu.

Et la colonne « Cours perdus » a **trois réponses distinctes**, jamais
deux (EF-A11) : rien du tout pour de vraies vacances (l'année est bâtie
autour d'elles), « aucun cours ce jour-là » pour une liste vide — la
bonne nouvelle — et la liste des classes quand ça coûte. Sans date de
référence de semaine A, on dit qu'on **ne sait pas** plutôt que d'inventer.

⚠️ **Le tableau n'est pas un ``ui.table``**, et c'est une décision. Un
tableau de composant rend des lignes homogènes ; ici il faut insérer des
séparateurs ENTRE des groupes de lignes, et la ligne de séparation porte
un texte calculé. C'est une grille, pas une table de données.
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

#: La largeur des colonnes du tableau des périodes. Une seule définition
#: pour l'en-tête ET les lignes : deux chaînes finiraient par diverger
#: d'un quart de colonne, ce qui ne se voit qu'à l'écran.
COLONNES = "grid-cols-[minmax(10rem,1.4fr)_9rem_9rem_6rem_minmax(12rem,1.6fr)]"


class ReglagesAnnee(PageState):
    """Le brouillon des quatre champs de l'année (EF-A1).

    ``annee_id`` n'est rendu par aucun champ et arrive quand même du
    navigateur : c'est un attribut déclaré du ``PageState``, donc le
    socle l'hydrate depuis le corps du POST. Il sert ici à détecter que
    le brouillon parle d'une AUTRE année que celle affichée — sans quoi
    changer d'année dans la barre latérale laisserait les quatre champs
    de la précédente.
    """

    annee_id: int = field(default=0)
    libelle: str = field(default="")
    debut: str = field(default="")
    fin: str = field(default="")
    lundi_ref: str = field(default="")


class ReglagesTrimestres(PageState):
    """Les six fins de trimestre : trois numéros × deux cycles (EF-A3).

    Six champs DÉCLARÉS plutôt qu'un dict, et c'est ce que la grille
    demande : elle a exactement six cases, connues à l'écriture. Un champ
    déclaré se lie par ``value=``, donc l'autoname lui donne son nom HTML
    et le socle l'hydrate — ce qu'un dict indexé ne peut pas faire.
    """

    annee_id: int = field(default=0)
    college_1: str = field(default="")
    college_2: str = field(default="")
    college_3: str = field(default="")
    lycee_1: str = field(default="")
    lycee_2: str = field(default="")
    lycee_3: str = field(default="")


class PeriodeDraft(PageState):
    """La période en cours d'édition, dans son dialogue.

    ``ouvert`` est un CHAMP booléen et pas une expression : un
    ``ui.dialog(open=…)`` piloté par le serveur exige un champ déclaré,
    sinon la valeur perd sa provenance et le dialogue ne s'ouvre jamais
    (le silence B3 de ``livrer-une-app.md``).

    ``libelle_origine`` retient le nom sous lequel la ligne est rangée en
    base. Sans lui, renommer une période en créerait une seconde et
    laisserait l'ancienne : la clé de la table est le NOM (EF-A4).
    """

    annee_id: int = field(default=0)
    ouvert: bool = field(default=False)
    libelle_origine: str = field(default="")
    libelle: str = field(default="")
    debut: str = field(default="")
    fin: str = field(default="")


class NouvelleAnnee(PageState):
    """Le brouillon de création d'année (EF-A2)."""

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
    """Les six cases d'un coup, y compris les vides.

    Une case vidée DOIT repartir au serveur, sinon on ne peut jamais
    retirer une date. C'est pour ça que l'enregistrement est global et
    non case par case : « je n'ai rien saisi » et « j'ai effacé » se
    ressemblent trait pour trait dans un POST partiel.
    """
    annee_id = int(form.annee_id)
    for cycle in CYCLES:
        for numero in (1, 2, 3):
            poser_trimestre(annee_id, cycle, numero,
                            str(getattr(form, f"{cycle}_{numero}")))
    ui.notification("Trimestres enregistrés", variant="success",
                    duration_ms=2000)


def ouvrir_periode(libelle: str, debut: str, fin: str) -> None:
    """Ouvre le dialogue sur une période — existante ou proposée."""
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


# ── Bloc 1 · l'année (EF-A1, EF-A2) ──────────────────────────────────

# ⚠️ `NouvelleAnnee` n'est PAS ici, et c'est le finding F12 : le
# brouillon appartient à `creation_dialogue()`, qui est une zone et le
# déclare déjà. Le porter ici ferait redessiner tout le bloc à chaque
# frappe dans le dialogue. La règle `zone-qui-ecoute-trop` le refuse.
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


# ── Bloc 2 · les trimestres (EF-A3) ──────────────────────────────────

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


# ── Bloc 3 · les périodes sans classe (EF-A4 … EF-A11) ───────────────

def lignes_du_tableau(annee: dict) -> list[dict]:
    """Les lignes à rendre : les périodes posées + les quatre proposées.

    EF-A4 : les vacances de zone B sont **proposées remplies ou non, sans
    créer de lignes vides à l'avance**. Une proposition est donc une
    ligne à l'écran et rien en base — elle n'existe que si on la remplit.

    EF-A6 : l'ordre est celui de l'ANNÉE, et ce qui n'a pas de date ferme
    la marche. Le tri par date vient de la requête (piège n° 13) ; ce qui
    se décide ici est seulement où mettre les propositions vides.
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
    """La colonne d'EF-A11 — trois réponses, jamais deux.

    L'ordre des tests EST la règle : on regarde d'abord si ce sont de
    vraies vacances (auquel cas il n'y a rien à dire), puis si
    l'alternance est calculable, et seulement ensuite ce que ça coûte.
    """
    debut = date.fromisoformat(ligne["debut"])
    fin = date.fromisoformat(ligne["fin"])
    if sont_de_vraies_vacances(debut, fin):
        # Rien. L'année est bâtie autour d'elles ; écrire « 43 heures
        # perdues » à côté de Noël serait du bruit exact et inutile.
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
                    # Le SEUL endroit du tableau où quelque chose coûte
                    # vraiment, donc le seul en rouge. Une heure ne se
                    # compte pas : « 4e1 » dit déjà tout.
                    ui.text(f" ×{heures}", color="error", weight="semibold")


def ligne_periode(annee: dict, ligne: dict, fige: bool) -> None:
    posee = bool(ligne["debut"])
    with ui.grid(gap="md", classes=f"{COLONNES} items-center py-2"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon("calendar-off" if posee else "calendar-plus",
                    color="muted")
            ui.text(ligne["libelle"], weight="medium" if posee else None,
                    color=None if posee else "muted")
        # EF-A7 : le jour de la semaine PRÉCÈDE la date, et l'année reste
        # affichée. EF-A8 : un férié montre ses DEUX dates, identiques —
        # une colonne à moitié vide se lit plus mal que deux colonnes
        # toujours remplies.
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


# ``PeriodeDraft`` n'apparaît pas ici : le bloc ne le lit pas. Il y
# était pour ``periode_dialogue``, que ce bloc appelait — donc ouvrir
# une période redessinait la liste entière.
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

        # EF-A9 : la ligne qui sépare les périodes de TRAVAIL. Elle
        # s'insère avant la première ligne dont le début tombe après
        # la fin du morceau — donc entre deux vraies vacances, et
        # jamais autour d'un férié.
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
    # Montés par la PAGE, pas par les blocs : cf. le commentaire sur
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
