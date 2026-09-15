"""features/eleve — page : la fiche d'un élève.

EF-C3 : *« sa photo, sa classe, ses notes du trimestre avec sa moyenne,
ses observations cochées, son appréciation, ses particularités et ses
vérifications en cours. »*

Sept choses, et quatre arrivent avec leur lot : les notes au 5, les
observations et l'appréciation au 6, les vérifications au 8. Le lot 4
livre les trois qui ne dépendent de rien — l'identité, les
particularités, et le **parcours** d'EF-C9, qui est la seule chose de
cette fiche que personne d'autre ne montre.

Pourquoi le parcours compte plus qu'il n'en a l'air
----------------------------------------------------
*« Les inscriptions sont datées précisément pour cela ; sans l'écran qui
les montre, l'historique est conservé et invisible. »* RT-2 fait porter à
chaque sortie une date au lieu d'effacer une ligne ; cet écran est la
seule raison pour laquelle cette date sert à quelque chose.
"""

from __future__ import annotations

from bretzel import Feature, abort, page, refreshable, ui
from bretzel.state import PageState, field
from examples.ecole.core.domain import AMENAGEMENTS, moyenne_de
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.appreciations import (
    VueEleveFiche,
    panneau_appreciation,
)
from examples.ecole.features.eleves_data import (
    classe_courante_de,
    eleve,
    parcours_de,
    regler_particularites,
)
from examples.ecole.features.notes_data import notes_du_trimestre
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import (
    VueSuiviEleve,
    dialogue_verification,
    panneau_verifications,
)


class VueEleve(PageState, addressable=True):
    """L'élève ouvert et le trimestre regardé (EF-U1).

    L'élève est dans le chemin ; seul le trimestre a besoin d'un nom
    d'URL, parce qu'il change ce que le serveur calcule. Mais
    ``eleve_id`` doit vivre dans l'état quand même : une zone
    ``@refreshable`` est rappelée sans argument, et le socle REFUSE
    qu'elle déclare un paramètre.
    """

    eleve_id: int = field(default=0)
    trimestre: int = field(default=1, url="t")


class Particularites(PageState):
    """Le brouillon des quatre particularités (EF-C4).

    ``eleve_id`` n'est rendu par aucun champ et arrive quand même : c'est
    un attribut déclaré, donc le socle l'hydrate depuis le POST. Il sert
    à détecter que le brouillon parle d'un AUTRE élève — sans quoi
    ouvrir une seconde fiche garderait les cases de la première.
    """

    eleve_id: int = field(default=0)
    amenagement: str = field(default="")
    vue_fragile: bool = field(default=False)
    gaucher: bool = field(default=False)
    precisions: str = field(default="")


def enregistrer_particularites(form: Particularites) -> None:
    regler_particularites(int(form.eleve_id), annee_regardee()["id"], {
        "amenagement": str(form.amenagement),
        "vue_fragile": bool(form.vue_fragile),
        "gaucher": bool(form.gaucher),
        "precisions": str(form.precisions),
    })
    ui.notification("Particularités enregistrées", variant="success",
                    duration_ms=2000)


@refreshable(deps=[AnneeVue, VueEleve, Particularites])
def panneau_particularites() -> None:
    eleve_id = int(VueEleve().eleve_id)
    fiche = eleve(eleve_id)
    if fiche is None:
        return
    form = Particularites()
    if int(form.eleve_id) != eleve_id:
        form.eleve_id = eleve_id
        form.amenagement = fiche["amenagement"]
        form.vue_fragile = bool(fiche["vue_fragile"])
        form.gaucher = bool(fiche["gaucher"])
        form.precisions = fiche["precisions"]
    fige = en_consultation()

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Particularités", level=2, size="lg")
        with ui.form(on_submit=enregistrer_particularites), ui.vstack(gap="md"):
            with ui.form_field(
                label="Aménagement",
                hint="PAP, PPS, PAI, PPRE — vide si aucun.",
            ):
                ui.select(
                    value=form.amenagement, disabled=fige,
                    options=[("", "Aucun"),
                             *((a, a) for a in AMENAGEMENTS)],
                )
            with ui.hstack(gap="lg", wrap=True):
                ui.switch(checked=form.vue_fragile,
                          label="Vue fragile", disabled=fige)
                ui.switch(checked=form.gaucher, label="Gaucher",
                          disabled=fige)
            with ui.form_field(
                label="Précisions",
                hint="Ce qui ne rentre dans aucune case.",
            ):
                ui.textarea(value=form.precisions, rows=3,
                            disabled=fige)
            with ui.hstack(justify="end"):
                ui.button("Enregistrer", type="submit",
                          color="primary", icon_left="save",
                          disabled=fige)


def changer_trimestre_eleve(vue: VueEleve) -> None:
    """Vide : la mutation seule re-rend les zones ``deps=[VueEleve]``."""


@refreshable(deps=[AnneeVue, VueEleve])
def panneau_notes() -> None:
    """Les notes du trimestre et la MOYENNE (EF-C3).

    La moyenne passe par :func:`~examples.ecole.core.domain.moyenne_de`,
    qui porte la règle du § 5.2 en entier : pondérée par le
    coefficient, chaque note ramenée sur 20 par son barème, et **les
    absences ne comptent pas** — elles ne valent pas zéro.
    """
    vue = VueEleve()
    eleve_id = int(vue.eleve_id)
    trimestre = int(vue.trimestre)
    courante = classe_courante_de(eleve_id)
    lignes = (notes_du_trimestre(eleve_id, courante["id"], trimestre)
              if courante else [])
    moyenne = moyenne_de([
        (li["valeur"], li["bareme"], li["coefficient"])
        for li in lignes if not li["absent"]
    ])

    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="baseline", wrap=True):
            ui.heading("Notes", level=2, size="lg")
            ui.text(
                f"Moyenne : {moyenne:.2f} / 20" if moyenne is not None
                else "Aucune note ce trimestre",
                color="muted",
            )
        ui.toggle_group(
            value=vue.trimestre,
            options=[(1, "Trimestre 1"), (2, "Trimestre 2"),
                     (3, "Trimestre 3")],
            on_change=changer_trimestre_eleve,
        )
        for ligne in ui.each(lignes, key="id"):
            with ui.hstack(gap="md", align="center", justify="between",
                           wrap=True):
                ui.link(label=ligne["nom"],
                        href=f"/evaluation/{ligne['id']}",
                        variant="underline")
                ui.text(f"{ligne['type']} · {ligne['date']}",
                        color="muted")
                if ligne["absent"]:
                    ui.badge(label="absent", color="warning",
                             variant="soft", size="xl")
                elif ligne["valeur"] is None:
                    ui.text("non saisie", color="muted")
                else:
                    ui.text(
                        f"{ligne['valeur']:g} / {ligne['bareme']:g}",
                        weight="semibold")


def panneau_parcours(eleve_id: int) -> None:
    """EF-C9 — les classes traversées, avec leurs dates."""
    etapes = parcours_de(eleve_id)
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        ui.heading("Parcours", level=2, size="lg")
        if len(etapes) <= 1:
            ui.text("Une seule inscription : aucun mouvement à montrer.",
                    color="muted")
        for etape in ui.each(etapes, key="debut"):
            with ui.hstack(gap="md", align="center", wrap=True):
                ui.icon("calendar" if etape["fin"] else "calendar-check",
                        color="muted" if etape["fin"] else "success")
                ui.text(etape["annee"], color="muted")
                ui.link(label=etape["code"],
                        href=f"/classe/{etape['classe_id']}",
                        variant="underline")
                ui.text(
                    f"du {etape['debut']} au {etape['fin']}"
                    if etape["fin"] else f"depuis le {etape['debut']}",
                    color="muted",
                )


@page("/eleve/{eleve_id}", layout=shell, title="Élève")
def eleve_page(eleve_id: int) -> None:
    fiche = eleve(int(eleve_id))
    if fiche is None:
        abort(404)
    # La page sème, la zone lit (cf. ``VueEleve``).
    vue = VueEleve()
    if int(vue.eleve_id) != int(eleve_id):
        vue.eleve_id = int(eleve_id)
    courante = classe_courante_de(int(eleve_id))
    # La fiche d'observation a besoin des TROIS : l'élève, sa classe
    # et le trimestre. Elle est semée ici pour la même raison que le
    # reste — une zone se re-rend hors du routage (cf. F4).
    observations = VueEleveFiche()
    observations.eleve_id = int(eleve_id)
    observations.classe_id = courante["id"] if courante else 0
    observations.trimestre = int(vue.trimestre)
    VueSuiviEleve().eleve_id = int(eleve_id)

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            if courante:
                ui.breadcrumb_item(label=courante["code"],
                                   href=f"/classe/{courante['id']}")
            ui.breadcrumb_item(label=f"{fiche['nom']} {fiche['prenom']}")

        with ui.hstack(gap="lg", align="center", wrap=True):
            ui.avatar(name=f"{fiche['prenom']} {fiche['nom']}", size="xl",
                      shape="circle")
            with ui.vstack(gap="none"):
                ui.heading(f"{fiche['nom'].upper()} {fiche['prenom']}",
                           level=1, size="2xl")
                ui.text(
                    courante["libelle"] if courante
                    else "Aucune inscription en cours",
                    color="muted",
                )

        panneau_notes()
        panneau_verifications()
        panneau_appreciation()
        with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
            panneau_particularites()
            panneau_parcours(int(eleve_id))
    dialogue_verification()


feature = Feature(
    name="eleve",
    kind="page",
    provides=[eleve_page, VueEleve, Particularites],
    uses=["eleves_data", "notes_data", "appreciations", "suivi",
          "annees", "shell"],
)
