"""features/plan — l'onglet « Plan » : asseoir une classe.

EF-G1 à EF-G17, et c'est le lot que le cahier annonce comme le plus
risqué : *« le seul qui demande un glisser-déposer arbitré par le serveur
avec des contraintes »*.

Comment le glisser marche ici
------------------------------
**Chaque PLACE est une zone de dépôt**, et elle n'accepte qu'un élève.
Le serveur arbitre au lâcher : il assied, et si la place était prise il
ÉCHANGE — un élève lâché sur une chaise occupée doit aller quelque part,
et l'endroit d'où il vient est le seul qui soit libre. Un refus, lui, ne
mute rien : le navigateur a déjà bougé la vignette, et le rendu serveur
la remet en place par le morph.

Ce que le plan refuse de faire, et c'est le piège n° 11
--------------------------------------------------------
*« Sur tablette, la main qui tient l'appareil effleure l'écran et déplace
un élève sans que rien ne le signale — on s'en aperçoit au cours suivant,
devant un plan faux. »* D'où EF-G14, et ses cinq clauses :

- le bouton dit ce qu'on va **pouvoir faire** — « Figer » / « Modifier »,
  jamais « Défiger », qui ne se lit pas ;
- figé, le glisser est **coupé** ET les boutons qui déplacent sont
  **grisés**, répartition automatique comprise. *« Protéger le geste le
  plus fin en laissant "Répartir" aurait été absurde. »* ;
- ce qui ne déplace personne reste ouvert : consulter, changer de salle,
  renommer, exporter ;
- le bouton est dans l'**en-tête**, pas dans la barre du plan : c'est en
  classe qu'il sert, précisément quand cette barre est repliée ;
- **l'état est retenu d'une ouverture à l'autre** — il vit en base.

⚠️ Aucune classe Tailwind n'est assemblée en f-string ; la largeur d'une
allée est un ``style=`` calculé, pour la même raison que les hauteurs de
la grille d'emploi du temps.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, abort, page, print_page, refreshable, ui
from bretzel.components import Move
from bretzel.state import PageState, field
from examples.ecole.core.placement import conflits, repartir, tables_de
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.eleves_data import classe, eleves_de
from examples.ecole.features.plan_data import (
    LARGEUR_ALLEE_DEFAUT,
    ContraintesRev,
    PlanRev,
    ajouter_salle,
    allonger,
    appliquer,
    asseoir,
    basculer_allee,
    basculer_devant,
    contraintes_de,
    figer,
    figer_version,
    places_de,
    poser_separation,
    premiere_salle,
    regler_largeur,
    restaurer_version,
    retirer_separation,
    salle,
    salles_de,
    separations_nommees,
    supprimer_salle,
    supprimer_version,
    tout_vider,
    tracer,
    versions_de,
)
from examples.ecole.features.shell import shell
from examples.ecole.features.vue_classe import VueClasse

#: Le groupe de glisser. Un seul : toutes les places acceptent les mêmes
#: vignettes, et c'est le serveur qui arbitre ce qui est légal.
GROUPE = "eleve"

#: La largeur d'une place, **en pixels**. Sert aussi à calculer celle
#: d'une allée, qui est en CENTIÈMES de place (EF-G6) — donc une
#: fraction de celle-ci.
#:
#: ⚠️ En ``px`` et plus en ``rem``, pour la raison écrite dans
#: ``emploi_du_temps.py`` : une salle de douze places sur douze
#: rangées ne tient à l'écran que si sa géométrie ne suit pas la
#: taille du texte. 76 px, c'est l'avatar du preset (32 px) plus son
#: nom court et le cadre en pointillés.
LARGEUR_PLACE = 76


class VuePlan(PageState, addressable=True):
    """La classe et la salle regardées (EF-U1 : *« la classe, la salle »*)."""

    classe_id: int = field(default=0)
    salle_id: int = field(default=0, url="salle")


class TraceDraft(PageState):
    """Le tracé d'EF-G2, dans son dialogue."""

    ouvert: bool = field(default=False)
    rangees: int = field(default=5)
    par_rangee: int = field(default=6)
    toutes_les: int = field(default=2)
    largeur: int = field(default=LARGEUR_ALLEE_DEFAUT)


class ContrainteDraft(PageState):
    """Une paire à séparer, en cours de saisie (EF-G10)."""

    ouvert: bool = field(default=False)
    eleve_a: str = field(default="")
    eleve_b: str = field(default="")


def salle_courante() -> dict | None:
    """La salle affichée — celle de l'adresse, ou la première.

    *« Une classe n'a pas de salle tant qu'on n'a pas ouvert son plan :
    la première est créée à la volée »* (EF-G11).
    """
    vue = VuePlan()
    classe_id = int(vue.classe_id) or int(VueClasse().classe_id)
    if not classe_id:
        return None
    demandee = int(vue.salle_id)
    connues = {s["id"] for s in salles_de(classe_id)}
    if demandee not in connues:
        demandee = premiere_salle(classe_id, annee_regardee()["id"])
        vue.salle_id = demandee
        vue.classe_id = classe_id
    return salle(demandee)


# ── Les handlers ─────────────────────────────────────────────────────

def deposer(m: Move) -> None:
    """Un élève lâché sur une place. **Le serveur arbitre.**

    ``m.to_zone`` est ``place_<id>`` ; ``m.item_key`` est l'identifiant
    de l'élève. Un plan FIGÉ ne mute rien, et c'est la seconde barrière :
    la première est ``locked=`` sur la zone, mais une zone verrouillée
    dans un DOM qu'on peut inspecter n'est pas une règle.
    """
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    if not m.to_zone.startswith("place_"):
        return
    asseoir(donnees["id"], donnees["annee_id"], int(m.to_zone[6:]),
            int(m.item_key))


def vider_place(place_id: int) -> None:
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    asseoir(donnees["id"], donnees["annee_id"], place_id, None)


def vider_tout() -> None:
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    tout_vider(donnees["id"], donnees["annee_id"])


def repartir_la_classe() -> None:
    """EF-G9 — et **jamais d'échec bloquant**.

    *« Au pire le tirage qui viole le moins de paires est retenu, et les
    conflits restants sont signalés. »* Un plan qu'on refuse de rendre
    laisse le professeur sans plan du tout.
    """
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    places = places_de(donnees["id"])
    eleves = eleves_pour(donnees)
    regles = contraintes_de(donnees["classe_id"])
    premier = not any(p["eleve_id"] for p in places)

    assises = repartir(
        eleves=eleves, places=places, devants=regles["devants"],
        separations=regles["separations"], premier_remplissage=premier,
    )
    appliquer(donnees["id"], donnees["annee_id"], assises)

    restants = conflits(assises, places, regles["separations"])
    if restants:
        noms = {e["id"]: f"{e['prenom']} {e['nom']}" for e in eleves}
        dit = " · ".join(f"{noms.get(a, a)} / {noms.get(b, b)}"
                         for a, b in restants[:3])
        ui.notification(
            dit, title=f"{len(restants)} paire(s) encore côte à côte",
            variant="warning", duration_ms=6000)
        return
    ui.notification(
        "Classe répartie, aucune contrainte violée."
        if premier is False else
        "Premier plan : par ordre alphabétique, depuis le fond.",
        variant="success", duration_ms=3000)


def eleves_pour(donnees: dict) -> list[dict]:
    """Les élèves que CETTE salle doit asseoir.

    EF-G17 : une salle de demi-groupe n'accueille que son groupe, et la
    répartition automatique ne brasse que lui.
    """
    tous = eleves_de(donnees["classe_id"])
    if donnees["demi_groupe"] is None:
        return tous
    return [e for e in tous if e["demi_groupe"] == donnees["demi_groupe"]]


def basculer_fige() -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    figer(donnees["id"], donnees["annee_id"], not donnees["fige"])


def changer_de_salle(salle_id: int) -> None:
    VuePlan().salle_id = salle_id


def nouvelle_salle(demi_groupe: int | None) -> None:
    vue = VuePlan()
    classe_id = int(vue.classe_id)
    nom = ("Laboratoire" if demi_groupe is None
           else f"TP groupe {demi_groupe}")
    vue.salle_id = ajouter_salle(classe_id, annee_regardee()["id"], nom,
                                 demi_groupe)


def retirer_salle() -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    refus = supprimer_salle(donnees["id"], donnees["annee_id"])
    if refus:
        ui.notification(refus, variant="warning", duration_ms=5000)
        return
    VuePlan().salle_id = 0


def allonger_rangee(rangee: int, delta: int) -> None:
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    refus = allonger(donnees["id"], donnees["annee_id"], rangee, delta)
    if refus:
        ui.notification(refus, variant="warning", duration_ms=5000)


def ouvrir_allee(colonne: int) -> None:
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    largeur = max((p["allee_avant"] for p in places_de(donnees["id"])),
                  default=0) or LARGEUR_ALLEE_DEFAUT
    refus = basculer_allee(donnees["id"], donnees["annee_id"], colonne,
                           largeur)
    if refus:
        ui.notification(refus, variant="warning", duration_ms=5000)


def ouvrir_trace(draft: TraceDraft) -> None:
    draft.ouvert = True


def fermer_trace(draft: TraceDraft) -> None:
    draft.ouvert = False


def appliquer_trace(draft: TraceDraft) -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    rangees = max(1, min(int(draft.rangees), 12))
    par_rangee = max(1, min(int(draft.par_rangee), 12))
    toutes_les = max(0, int(draft.toutes_les))
    allees = ([c for c in range(2, par_rangee + 1)
               if toutes_les and (c - 1) % toutes_les == 0]
              if toutes_les else [])
    tracer(donnees["id"], donnees["annee_id"], [par_rangee] * rangees,
           allees, int(draft.largeur))
    draft.ouvert = False


def regler_la_largeur(draft: TraceDraft) -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    regler_largeur(donnees["id"], donnees["annee_id"], int(draft.largeur))


def ouvrir_contrainte(draft: ContrainteDraft) -> None:
    draft.ouvert = True


def fermer_contrainte(draft: ContrainteDraft) -> None:
    draft.ouvert = False


def enregistrer_contrainte(draft: ContrainteDraft) -> None:
    donnees = salle_courante()
    if donnees is None or not (draft.eleve_a and draft.eleve_b):
        return
    poser_separation(donnees["classe_id"], donnees["annee_id"],
                     int(draft.eleve_a), int(draft.eleve_b))
    draft.ouvert = False


def retirer_la_separation(separation_id: int) -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    retirer_separation(separation_id, donnees["annee_id"])


def basculer_le_devant(eleve_id: int) -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    basculer_devant(donnees["classe_id"], donnees["annee_id"], eleve_id)


def enregistrer_version() -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    figer_version(donnees["id"], donnees["annee_id"], "")
    ui.notification("Version enregistrée", variant="success",
                    duration_ms=2000)


def restaurer(version_id: int) -> None:
    donnees = salle_courante()
    if donnees is None or donnees["fige"]:
        return
    restaurer_version(version_id, donnees["annee_id"])


def supprimer_la_version(version_id: int) -> None:
    donnees = salle_courante()
    if donnees is None:
        return
    supprimer_version(version_id, donnees["annee_id"])


# ── Le rendu ─────────────────────────────────────────────────────────

def chaise(place: dict, fige: bool, en_table: bool) -> None:
    """Une place : une zone de dépôt qui n'accueille qu'un élève.

    L'allée qui la précède est un ``style=`` calculé — sa largeur est en
    CENTIÈMES de place (EF-G6), donc une fraction d'une largeur connue,
    et une classe Tailwind ne sait pas multiplier.
    """
    if place["allee_avant"]:
        ui.flex(
            style=f"width:{place['allee_avant'] / 100 * LARGEUR_PLACE}px")
    with ui.dropzone(
        # `holds="one"` : une chaise ne tient qu'UN élève. Sans lui, le
        # geste glissait l'élève dans la chaise visée le temps du survol,
        # qui en portait alors deux — la chaise s'ouvrait, le plan se
        # décalait, et on ne voyait plus où l'on posait. Avec, la chaise
        # ne bouge pas et s'annonce écrasable ; l'échange reste le fait
        # d'`asseoir`, côté serveur, qui le faisait déjà.
        name=f"place_{place['id']}", accepts=[GROUPE], holds="one",
        on_move=deposer,
        locked=fige, color="primary",
        classes="rounded-lg border border-dashed border-text/20 p-1 "
                + ("border-solid border-text/30" if en_table else ""),
        style=f"width:{LARGEUR_PLACE}px",
    ):
        if place["eleve_id"]:
            for assis in ui.drag_each([place], group=GROUPE,
                                      key=lambda p: str(p["eleve_id"]),
                                      disabled=lambda _p: fige):
                vignette_assise(assis, fige)
        else:
            # ``align=`` / ``justify=`` et pas ``classes=`` : les deux
            # props émettent DÉJÀ une classe sur cet élément, et deux
            # classes de même spécificité laissent la feuille Tailwind
            # trancher — le HTML porte les deux et rien ne dit laquelle
            # a gagné. `bretzel check` l'a dit avant qu'on le voie.
            ui.flex(align="center", justify="center", classes="h-12",
                    style=f"width:{LARGEUR_PLACE - 12}px")


def vignette_assise(place: dict, fige: bool) -> None:
    with ui.vstack(gap="none", align="center", classes="p-1"):
        ui.avatar(name=f"{place['prenom']} {place['nom']}", size="lg",
                  shape="circle")
        ui.text(place["prenom"], truncate=True)
        ui.text(place["nom"].upper(), color="muted", truncate=True)
        with ui.hstack(gap="none", justify="center"):
            if place["amenagement"]:
                ui.icon("badge-alert", color="info",
                        tooltip=place["amenagement"])
            if place["vue_fragile"]:
                ui.icon("eye", color="warning", tooltip="Vue fragile")
            if place["gaucher"]:
                ui.icon("hand", color="muted", tooltip="Gaucher")
            if not fige:
                ui.icon_button("x", variant="ghost",
                               aria_label=f"Retirer {place['prenom']}",
                               on_click=partial(vider_place, place["id"]))


@refreshable(deps=[AnneeVue, VuePlan, PlanRev])
def panneau_plan() -> None:
    """La SALLE : la barre, les places, la liste d'attente. Rien d'autre.

    **Ce qui n'est PAS ici, et pourquoi.** Une zone est le grain de ce
    qu'on redessine : tout ce qu'on y appelle repart à chaque geste,
    même ce qui n'a pas bougé. Trois surfaces en sortaient donc, et
    c'est mesuré le 2026-09-13 sur un simple « vider une place » —
    **248 ko de réponse** :

    - les deux dialogues, **67 ko**, alors qu'ils sont FERMÉS. Ils sont
      des zones à eux depuis F12 (leur brouillon ne redessine plus la
      salle), mais les APPELER ici les remettait dans le paquet : une
      zone imbriquée repart avec celle qui la contient, le découplage
      ne joue que dans un sens. Ils sont montés par la page ;
    - la colonne des contraintes, **~40 ko**, qui suit maintenant
      :class:`ContraintesRev` — asseoir un élève ne change ni une paire
      à séparer ni une version.

    Ce que le plan doit suivre, c'est l'EFFET d'une écriture de place,
    et il passe par :class:`PlanRev`.
    """
    donnees = salle_courante()
    if donnees is None:
        ui.empty_state(title="Aucune classe", icon="users")
        return
    fige = bool(donnees["fige"]) or en_consultation()
    places = places_de(donnees["id"])
    eleves = eleves_pour(donnees)
    assis = {p["eleve_id"] for p in places if p["eleve_id"]}
    debout = [e for e in eleves if e["id"] not in assis]
    en_table = {p for paire in tables_de(places) for p in paire}
    rangees = sorted({p["rangee"] for p in places})

    with ui.vstack(gap="md"):
        barre_du_plan(donnees, fige, len(debout))
        with ui.card(padding="md"), ui.vstack(gap="sm"):
            ui.text("Tableau", color="muted", align="center",
                    classes="border-b-2 border-text/20 pb-1")
            for rangee in rangees:
                with ui.hstack(gap="sm", align="center"):
                    for place in [p for p in places if p["rangee"] == rangee]:
                        chaise(place, fige, place["id"] in en_table)
                    if not fige:
                        ui.icon_button(
                            "minus", variant="ghost", size="sm",
                            aria_label=f"Retirer une place rangée {rangee}",
                            on_click=partial(allonger_rangee, rangee, -1))
                        ui.icon_button(
                            "plus", variant="ghost", size="sm",
                            aria_label=f"Ajouter une place rangée {rangee}",
                            on_click=partial(allonger_rangee, rangee, 1))
            if not fige:
                boutons_dallees(places)
        salle_dattente(debout, fige)


def boutons_dallees(places: list[dict]) -> None:
    """EF-G4 — un bouton par COLONNE, jamais par place.

    *« Un passage ouvert sur trois rangées et fermé sur deux ne
    ressemble à aucune salle réelle. »* La colonne 1 n'a pas de bouton :
    une allée devant la première place est refusée (EF-G5), et un bouton
    qui ne peut que refuser n'a rien à faire à l'écran.
    """
    colonnes = sorted({p["colonne"] for p in places})
    with ui.hstack(gap="sm", align="center", wrap=True):
        ui.text("Allées :", color="muted")
        for colonne in colonnes:
            if colonne == 1:
                continue
            ouverte = any(p["allee_avant"] for p in places
                          if p["colonne"] == colonne)
            ui.button(
                f"avant {colonne}",
                variant="solid" if ouverte else "outline",
                on_click=partial(ouvrir_allee, colonne),
            )


def salle_dattente(debout: list[dict], fige: bool) -> None:
    """Les élèves pas encore assis. C'est d'ici qu'on les glisse."""
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.heading(f"Pas encore assis · {len(debout)}", level=3, size="md")
        if not debout:
            ui.text("Tout le monde est placé.", color="muted")
        with ui.dropzone(name="attente", accepts=[GROUPE], on_move=deposer,
                         locked=True), ui.hstack(gap="sm", wrap=True):
            for eleve in ui.drag_each(debout, group=GROUPE,
                                      key=lambda e: str(e["id"]),
                                      disabled=lambda _e: fige):
                with ui.vstack(gap="none", align="center",
                               classes="p-1 rounded-lg border "
                                       "border-text/10"):
                    ui.avatar(name=f"{eleve['prenom']} {eleve['nom']}",
                              size="md", shape="circle")
                    ui.text(eleve["prenom"], truncate=True)


def barre_du_plan(donnees: dict, fige: bool, debout: int) -> None:
    # Meme raison que dans `colonne_des_contraintes` : `en_consultation()`
    # coute deux requetes, donc on le lit une fois pour la barre.
    consultation = en_consultation()
    with ui.hstack(gap="md", justify="between", align="center", wrap=True):
        with ui.hstack(gap="sm", align="center", wrap=True):
            for autre in salles_de(donnees["classe_id"]):
                ui.button(
                    autre["nom"] + (f" · TP {autre['demi_groupe']}"
                                    if autre["demi_groupe"] else ""),
                    variant="solid" if autre["id"] == donnees["id"]
                    else "outline",
                    on_click=partial(changer_de_salle, autre["id"]),
                )
            if not consultation:
                ui.icon_button("plus", variant="ghost",
                               aria_label="Ajouter une salle",
                               on_click=partial(nouvelle_salle, None))
        with ui.hstack(gap="sm", align="center", wrap=True):
            # EF-G14 : ce qui ne déplace personne reste ouvert même figé.
            ui.button("Imprimer", variant="ghost", icon_left="printer",
                      on_click=print_page())
            ui.button("Enregistrer une version", variant="ghost",
                      icon_left="camera", on_click=enregistrer_version)
            ui.button("Tracer la salle", variant="outline",
                      icon_left="grid-3x3", disabled=fige,
                      on_click=ouvrir_trace)
            ui.button("Tout vider", variant="ghost", icon_left="eraser",
                      disabled=fige, on_click=vider_tout)
            ui.button(f"Répartir ({debout} debout)", variant="outline",
                      icon_left="shuffle", disabled=fige,
                      on_click=repartir_la_classe)


@refreshable(deps=[AnneeVue, VuePlan, PlanRev])
def bouton_figer() -> None:
    """EF-G14 — **dans l'en-tête, pas dans la barre du plan**.

    *« C'est en classe qu'il sert, précisément quand cette barre est
    repliée. »* Et le libellé dit ce qu'on va POUVOIR FAIRE : « Figer » /
    « Modifier », jamais « Défiger », qui ne se lit pas.
    """
    donnees = salle_courante()
    if donnees is None:
        return
    fige = bool(donnees["fige"])
    ui.button(
        "Modifier" if fige else "Figer",
        variant="solid" if fige else "outline",
        color="warning" if fige else None,
        icon_left="lock-open" if fige else "lock",
        disabled=en_consultation(),
        on_click=basculer_fige,
    )


@refreshable(deps=[AnneeVue, VuePlan, ContraintesRev])
def colonne_des_contraintes() -> None:
    """EF-G10 et EF-G13 — les contraintes de la CLASSE, et les versions.

    Zone à part depuis le 2026-09-13 : elle ne dépend PAS de
    :class:`PlanRev`, donc elle ne repart pas à chaque élève déplacé.
    Elle lit ses propres entrées — une zone ne reçoit pas d'arguments,
    c'est ce qui lui permet de se re-rendre seule.
    """
    donnees = salle_courante()
    if donnees is None:
        return
    eleves = eleves_pour(donnees)
    fige = bool(donnees["fige"]) or en_consultation()
    regles = contraintes_de(donnees["classe_id"])
    # ⚠️ **Une seule lecture pour toute la colonne.** `en_consultation()`
    # coute DEUX requetes SQL : il compare l'annee regardee a l'annee en
    # cours, et chacune relit la table des annees. Ecrit dans les boucles
    # ci-dessous — une par contrainte, une par eleve, une par version — il
    # partait une fois par bouton : **228 requetes identiques pour un seul
    # rendu**, soit 90 % des 955 ms que la page coutait. Une zone lit ses
    # entrees en tete, pas a chaque widget.
    consultation = en_consultation()
    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
        with ui.card(padding="md"), ui.vstack(gap="sm"):
            with ui.hstack(justify="between", align="center", wrap=True):
                ui.heading("À séparer", level=3, size="md")
                ui.button("Ajouter", variant="ghost", icon_left="plus",
                          disabled=consultation,
                          on_click=ouvrir_contrainte)
            ui.text(
                "Attachées à la CLASSE, pas à la salle : elles valent pour "
                "tous ses plans.",
                color="muted",
            )
            for paire in ui.each(separations_nommees(donnees["classe_id"]),
                                 key="id"):
                with ui.hstack(gap="sm", align="center", wrap=True):
                    ui.text(f"{paire['prenom_a']} {paire['nom_a'].upper()}"
                            f" / {paire['prenom_b']} "
                            f"{paire['nom_b'].upper()}")
                    ui.icon_button("x", variant="ghost",
                                   aria_label="Retirer cette contrainte",
                                   disabled=consultation,
                                   on_click=partial(retirer_la_separation,
                                                    paire["id"]))
        with ui.card(padding="md"), ui.vstack(gap="sm"):
            ui.heading("À mettre devant", level=3, size="md")
            ui.text(
                "L'aménagement, la vue fragile et le choix manuel se "
                "CUMULENT : les trois mettent devant.",
                color="muted",
            )
            with ui.hstack(gap="sm", wrap=True):
                for eleve in eleves:
                    impose = eleve["amenagement"] or eleve["vue_fragile"]
                    ui.button(
                        eleve["prenom"],
                        variant="solid" if eleve["id"] in regles["devants"]
                        else "outline",
                        color="info" if impose else None,
                        disabled=consultation,
                        tooltip=("Aménagement ou vue fragile : devant de "
                                 "toute façon" if impose else None),
                        on_click=partial(basculer_le_devant, eleve["id"]),
                    )
            ui.divider(label="Versions")
            for version in ui.each(versions_de(donnees["id"]), key="id"):
                with ui.hstack(gap="sm", align="center", wrap=True):
                    ui.text(f"{version['nom']} · {version['cree_le']}")
                    ui.button("Restaurer", variant="ghost", disabled=fige,
                              on_click=partial(restaurer, version["id"]))
                    ui.icon_button(
                        "trash-2", variant="ghost",
                        aria_label="Supprimer cette version",
                        disabled=consultation,
                        on_click=partial(supprimer_la_version,
                                         version["id"]))


@refreshable(deps=[TraceDraft])
def dialogue_trace() -> None:
    draft = TraceDraft()
    with (
        ui.dialog(open=draft.ouvert, title="Tracer la salle",
                  on_close=fermer_trace),
        ui.form(on_submit=appliquer_trace),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "La grille est refaite entièrement : les élèves assis "
            "retournent en attente.",
            color="muted",
        )
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Rangées"):
                ui.number_input(value=draft.rangees, min=1, max=12, step=1)
            with ui.form_field(label="Places par rangée"):
                ui.number_input(value=draft.par_rangee, min=1, max=12,
                                step=1)
            with ui.form_field(label="Une allée toutes les",
                               hint="0 : aucune allée."):
                ui.number_input(value=draft.toutes_les, min=0, max=6, step=1)
            with ui.form_field(
                label="Largeur d'allée",
                hint="En centièmes de place. Une salle a UN passage.",
            ):
                ui.number_input(value=draft.largeur, min=0, max=200, step=10)
        with ui.hstack(gap="md", justify="end"):
            ui.button("Appliquer la largeur seule", variant="ghost",
                      on_click=regler_la_largeur)
            ui.button("Tracer", type="submit", color="primary")


@refreshable(deps=[ContrainteDraft, VuePlan])
def dialogue_contrainte() -> None:
    draft = ContrainteDraft()
    donnees = salle_courante()
    options = ([(str(e["id"]), f"{e['prenom']} {e['nom']}")
                for e in eleves_de(donnees["classe_id"])]
               if donnees else [])
    with (
        ui.dialog(open=draft.ouvert, title="Deux élèves à séparer",
                  on_close=fermer_contrainte),
        ui.form(on_submit=enregistrer_contrainte),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "La contrainte suit la CLASSE : elle vaudra dans toutes ses "
            "salles, et la répartition automatique essaiera de la tenir.",
            color="muted",
        )
        with ui.form_field(label="Premier élève", required=True):
            ui.select(value=draft.eleve_a, options=options)
        with ui.form_field(label="Second élève", required=True):
            ui.select(value=draft.eleve_b, options=options)
        with ui.hstack(justify="end"):
            ui.button("Les séparer", type="submit", color="primary")


@page("/plan/{classe_id}", layout=shell, title="Plan de classe")
def plan_page(classe_id: int) -> None:
    donnees = classe(int(classe_id))
    if donnees is None:
        abort(404)
    vue = VuePlan()
    if int(vue.classe_id) != int(classe_id):
        vue.classe_id = int(classe_id)
        vue.salle_id = 0

    with ui.vstack(gap="lg"):
        with ui.breadcrumb():
            ui.breadcrumb_item(label="Mes classes", href="/classes",
                               icon="layout-grid")
            ui.breadcrumb_item(label=donnees["code"],
                               href=f"/classe/{classe_id}")
            ui.breadcrumb_item(label="Plan")
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.heading(f"Plan de classe · {donnees['code']}", level=1,
                       size="2xl")
            bouton_figer()
        panneau_plan()
        colonne_des_contraintes()
    # Hors de la pile : montés par la PAGE, pas par la salle. Une zone
    # appelée dans une autre repart avec elle, et ces deux-là pesaient
    # 67 ko sur chaque glisser alors qu'elles sont fermées.
    dialogue_trace()
    dialogue_contrainte()


feature = Feature(
    name="plan",
    kind="page",
    provides=[plan_page, panneau_plan, colonne_des_contraintes,
              bouton_figer, VuePlan, TraceDraft, ContrainteDraft],
    uses=["plan_data", "eleves_data", "annees", "shell", "vue_classe"],
)
