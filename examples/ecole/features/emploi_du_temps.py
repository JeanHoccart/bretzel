"""features/emploi_du_temps — page : la grille de la semaine. L'ouverture.

*« C'est l'écran d'ouverture »* (§ 8 du cahier), et c'est l'écran des
vingt secondes sur le pas de la porte. EF-B1 à EF-B14.

Les trois modes, et pourquoi ce sont trois et pas deux
------------------------------------------------------
========================  ==================================================
mode                      ce qu'on y fait
========================  ==================================================
**lecture** (le défaut)   on regarde la semaine. Les jours sans classe
                          sont VIDES et portent le nom de leur période
**modification**          on reprend la grille TYPE. *« C'est pendant les
                          vacances qu'on a le temps de reprendre la
                          grille »* — donc **tout revient** (EF-B5)
**exceptions**            on pose une heure en plus ou une annulation sur
                          une VRAIE date (EF-B11)
========================  ==================================================

Ils sont trois parce que les deux derniers n'écrivent pas la même chose :
la modification touche la grille qui se répète, l'exception touche un
jour précis. Les confondre, c'est annuler tous les lundis en croyant
annuler celui-ci.

Ce que l'écran REFUSE d'afficher, et c'est le piège n° 12
---------------------------------------------------------
*« Griser les jours de vacances en laissant lire les classes ne suffit
pas — on lit quand même cinq cours qu'on ne fera pas. »* Un jour sans
classe est donc VIDE, et le nom de la période est écrit sous la date
(EF-B4). En mode modification, il redevient plein : la grille type n'est
jamais effacée, ce sont les jours qui ne l'appliquent pas.

Et ce qu'il refuse de construire
---------------------------------
**Pas de bandeau « Maintenant : 4e3 »** (EF-B16). Il a été construit puis
retiré dans les DEUX applications réelles, pour la même raison : la
grille est juste en dessous et dit la même chose en mieux, et le bandeau
occupait la première ligne de l'écran même sans rien à dire.

⚠️ La mise en page n'est pas une grille CSS à ``row-span``
-----------------------------------------------------------
Elle l'a été une heure, et c'est faux : le placement automatique d'une
grille CSS est SÉQUENTIEL, donc une case qui déborde de trois rangées
décale toutes les suivantes d'une colonne — le mercredi se retrouve sous
le mardi. Ici, **sept colonnes qui empilent chacune leurs cases**, toutes
à la même hauteur, et un bloc de trois heures prend la hauteur de trois
cases par un ``style=`` calculé. Les colonnes restent alignées parce que
chaque case pèse exactement pareil.

⚠️ Et aucune classe Tailwind n'est ASSEMBLÉE en f-string : une classe
construite (``bg-{couleur}/5``) n'existe qu'en développement, où le
compilateur tourne dans le navigateur — en production elle disparaît sans
une erreur. Les trois teintes sont donc des chaînes ENTIÈRES, dans une
table finie.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from functools import partial

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field
from bretzel.theme import DEFAULT_SPACING_PX
from examples.ecole.core.domain import JOURS, est_un_tp, jour_et_date
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    en_consultation,
)
from examples.ecole.features.grille_data import (
    annuler_derniere_grille,
    classe_id_de,
    lundi_affiche,
    poser_case,
    poser_exception,
    regler_horaire,
    retirer_exception,
    semaine_affichee,
)
from examples.ecole.features.shell import shell
from examples.ecole.features.suivi import cadres_du_jour

PATH = "/"

#: Sept colonnes : les horaires, puis les six jours.
#:
#: ⚠️ **En ``px``, pas en ``rem``.** Une largeur écrite en ``rem``
#: suit la taille du texte, et la semaine cesse de tenir à l'écran
#: dès que celle-ci bouge. Mesuré avec la base à 19 px que l'app
#: portait un temps : la grille réclamait 1 178 px à elle seule, et
#: vendredi et samedi passaient derrière une barre de défilement —
#: sur l'écran dont TOUT le propos est de se lire d'un coup d'œil.
#: La largeur d'une colonne appartient à l'écran, pas au texte.
COLONNES = "grid-cols-[56px_repeat(6,minmax(88px,1fr))]"

#: La hauteur d'UNE heure et l'espace entre deux, **en pixels**. Les
#: deux servent à calculer la hauteur d'un bloc de N heures — d'où des
#: nombres et pas des classes : ``h-24`` ne sait pas additionner.
#:
#: 64 px, et le calcul vaut d'être écrit parce qu'il s'est trompé
#: trois fois. Une case montre DEUX lignes — le code de la classe, puis
#: la salle et le lien vers le cahier — soit 42 px de texte à l'échelle
#: du preset (14 px, interligne normal). Le reste est le CADRE :
#: ``ui.card(padding="xs")`` pose 8 px de chaque côté, plus un liseré.
#: Une carte a ``overflow:hidden``, donc tout ce qui ne rentre pas dans
#: ce compte disparaît **sans un mot** — pas d'erreur, pas de trace, et
#: un HTML complet.
#:
#: ⚠️ 72 et pas 64 : le compte « deux lignes plus le cadre » était
#: juste et INCOMPLET — un lien souligné descend sous sa ligne de base,
#: et la carte a un liseré. Le probe a rendu le chiffre exact (68), la
#: tête en donnait 60. C'est la quatrième valeur de la journée, et la
#: seule qu'on n'ait pas devinée.
#:
#: L'historique dit pourquoi le constat (24) du probe existe : 52 px,
#: une heure perdait sa salle ; 64 px avec ``padding="sm"``, le cadre
#: mangeait 32 px des 62 utilisables et il en fallait 80 ; 80 px avec
#: le preset, deux tiers de la case étaient vides. C'est le finding F9,
#: et aucune de ces trois valeurs n'était devinable en lisant le code.
HAUTEUR_CASE = 72

#: L'espace entre deux cases, **DÉRIVÉ et plus recopié**.
#:
#: Les colonnes sont des ``ui.vstack(gap="xs")``, soit ``gap-1``, soit
#: un cran d'espacement. Le lire depuis le préréglage au lieu de l'écrire
#: ici supprime la classe entière du finding F10 : la valeur ne peut
#: plus diverger de celle que la colonne pose vraiment.
#:
#: ⚠️ Elle avait divergé deux fois. 6 px pour un ``gap-1`` de 4, puis
#: 4 pour un ``gap-1`` devenu 3 quand la densité est passée à 3 px le
#: pas. Le défaut ne se voit sur aucune case d'une heure — il ne sert
#: qu'aux BLOCS, qui glissent d'autant par heure supplémentaire.
ESPACE_CASE = DEFAULT_SPACING_PX

#: Le pas d'une rangée : la case plus son espace. C'est la période du
#: filet de fond, et la seule façon que les lignes tombent PILE entre
#: deux cases.
PAS_RANGEE = HAUTEUR_CASE + ESPACE_CASE

#: Le filet horizontal des vrais calendriers, dessiné en FOND.
#:
#: ⚠️ **En fond et pas en bordure**, et c'est ce qui change tout. Une
#: bordure vit sur une case, donc elle s'arrête là où il y a une case :
#: la grille était un damier de cartes flottant dans du vide, sans
#: repère pour aligner un cours sur son heure. Le fond, lui, ne dépend
#: d'aucun contenu — il continue sous les blocs et à travers les heures
#: creuses, exactement comme la trame d'un agenda.
#:
#: ⚠️ Un gris neutre à faible opacité plutôt qu'un jeton de thème : la
#: même valeur doit tenir sur le papier clair et sur le gris sombre, et
#: un filet qui suit la couleur du texte disparaît d'un côté ou crie de
#: l'autre.
FILET = "rgba(128,128,128,0.16)"


def fond_de_colonne(rangs: int) -> str:
    """Le ``style=`` d'une colonne : sa hauteur et sa trame.

    La trame se répète sur :data:`PAS_RANGEE` et pose son filet sur le
    dernier pixel — donc dans l'espace inter-cases, jamais sous une
    carte.
    """
    haut = rangs * HAUTEUR_CASE + (rangs - 1) * ESPACE_CASE
    return (
        f"height:{haut}px;"
        f"background-image:repeating-linear-gradient(to bottom,"
        f"transparent 0,transparent {HAUTEUR_CASE}px,"
        f"{FILET} {HAUTEUR_CASE}px,{FILET} {HAUTEUR_CASE + 1}px,"
        f"transparent {HAUTEUR_CASE + 1}px,transparent {PAS_RANGEE}px)"
    )

#: La hauteur d'un en-tête de colonne, **fixe pour les sept**.
#:
#: ⚠️ Sans hauteur fixe, chaque colonne se dimensionne sur SON
#: contenu : un jour de vacances porte une ligne de plus (le nom de
#: la période, EF-B4), donc SA colonne descend d'un cran et ses cases
#: cessent d'être en face des horaires. Le décalage n'apparaît que
#: les semaines de vacances, ce qui est la pire façon de le trouver.
#:
#: 44 px : deux lignes courtes à l'échelle du preset, plus le filet.
HAUTEUR_ENTETE = 44

#: Les trois teintes d'une case, en chaînes ENTIÈRES. Une table finie,
#: parce qu'une classe assemblée n'existe qu'en dev (cf. l'en-tête).
#: ⚠️ **Pas de cadre complet, un liseré à GAUCHE.** Un contour sur les
#: quatre côtés se lit comme un bouton ; c'est le cas de tous les
#: agendas qui valent d'être copiés — l'événement est une surface
#: teintée que sa barre de gauche identifie. Trente contours dans une
#: grille font un damier, trente surfaces font une semaine.
#: Chaînes ENTIÈRES, jamais assemblées : une classe fabriquée en
#: f-string n'existe pas dans la feuille de prod.
TEINTES: dict[str, str] = {
    "cours": ("bg-primary/12 border-l-[3px] border-l-primary "
              "rounded-r-md overflow-hidden px-2 py-1"),
    "nature": ("bg-warning/12 border-l-[3px] border-l-warning "
               "rounded-r-md overflow-hidden px-2 py-1"),
    "exception": ("bg-info/12 border-l-[3px] border-l-info "
                  "rounded-r-md overflow-hidden px-2 py-1"),
}

#: Les trois modes, leur libellé et leur icône.
MODES: tuple[tuple[str, str, str], ...] = (
    ("lecture", "Lecture", "eye"),
    ("modification", "Modifier la grille", "pencil"),
    ("exceptions", "Heures exceptionnelles", "calendar-clock"),
)


class SemaineVue(PageState, addressable=True):
    """La semaine affichée — **et l'adresse en fait foi** (EF-U1).

    *« Un écran qu'on ne peut pas renvoyer par un lien n'est pas
    partageable avec soi-même le lendemain »* : ``/?semaine=2026-11-16``
    ouvre cette semaine-là chez qui reçoit le lien.

    Vide = la semaine d'aujourd'hui. Un défaut CALCULÉ serait figé au
    démarrage du processus et faux le lendemain ; un défaut vide reste
    juste tous les jours.
    """

    lundi: str = field(default="", url="semaine")


class ModeGrille(PageState):
    """Le mode de la grille, et la case en cours d'édition.

    ``PageState`` sans adresse : un mode n'est pas *ce qu'on regarde*
    mais *ce qu'on est en train de faire*. Le mettre dans l'URL ouvrirait
    l'écran de celui qui reçoit le lien en modification.
    """

    mode: str = field(default="lecture")
    ouvert: bool = field(default=False)
    jour: int = field(default=0)
    rang: int = field(default=1)
    date_iso: str = field(default="")
    occupee: bool = field(default=False)
    saisie: str = field(default="")


class HoraireDraft(PageState):
    """Les bornes d'un créneau, réglées pour toute l'année (EF-B3)."""

    ouvert: bool = field(default=False)
    rang: int = field(default=1)
    debut: str = field(default="")
    fin: str = field(default="")


def hauteur(rangs: int) -> str:
    """Le ``style=`` d'une case qui couvre ``rangs`` heures."""
    total = rangs * HAUTEUR_CASE + (rangs - 1) * ESPACE_CASE
    return f"height:{total}px"


# ── Les handlers ─────────────────────────────────────────────────────

def aller_a(decalage: int) -> None:
    """Les flèches de semaine (EF-B1). ``0`` ramène à aujourd'hui."""
    vue = SemaineVue()
    if decalage == 0:
        vue.lundi = ""
        return
    courant = lundi_affiche(annee_regardee(), str(vue.lundi))
    vue.lundi = (courant + timedelta(weeks=decalage)).isoformat()


def changer_mode(mode: str) -> None:
    etat = ModeGrille()
    etat.mode = mode
    etat.ouvert = False


def ouvrir_case(jour: int, rang: int, date_iso: str, occupee: bool,
                saisie: str) -> None:
    etat = ModeGrille()
    etat.jour = jour
    etat.rang = rang
    etat.date_iso = date_iso
    etat.occupee = occupee
    etat.saisie = saisie
    etat.ouvert = True


def fermer_case(etat: ModeGrille) -> None:
    etat.ouvert = False


def lettre_affichee() -> str | None:
    """La lettre de la semaine affichée — DÉDUITE, jamais choisie (EF-B2)."""
    annee = annee_regardee()
    lundi = lundi_affiche(annee, str(SemaineVue().lundi))
    return semaine_affichee(annee, lundi)["lettre"]


def enregistrer_case(etat: ModeGrille) -> None:
    """Le geste d'EF-B6 : on tape un code, la case le prend.

    La lettre vient de la semaine AFFICHÉE et n'est donc pas un champ du
    formulaire : elle ne se choisit pas. Sans date de référence, on ne
    sait pas quelle moitié de la grille on écrit — et écrire quand même
    poserait le cours une semaine sur deux, au hasard.
    """
    lettre = lettre_affichee()
    if not lettre:
        ui.notification(
            "Sans date de référence de semaine A, on ne sait pas quelle "
            "semaine on modifie. À régler dans les Réglages.",
            variant="warning", duration_ms=5000)
        etat.ouvert = False
        return
    code = poser_case(annee_regardee()["id"], int(etat.jour), int(etat.rang),
                      lettre, str(etat.saisie))
    etat.ouvert = False
    ui.notification(
        f"{code} posée en semaine {lettre}" if code else "Case vidée",
        variant="success", duration_ms=2000)


def annuler_lheure(etat: ModeGrille) -> None:
    """Une case OCCUPÉE ne propose qu'une annulation (EF-B11).

    *On n'est pas à deux endroits à la fois* : proposer d'ajouter une
    classe sur une heure déjà prise n'aurait aucun sens.
    """
    poser_exception(annee_regardee()["id"], str(etat.date_iso),
                    int(etat.rang), "")
    etat.ouvert = False


def ajouter_lheure(etat: ModeGrille) -> None:
    """Une case LIBRE ne propose qu'un ajout — il n'y a rien à y annuler."""
    code = str(etat.saisie).strip()
    if code:
        poser_exception(annee_regardee()["id"], str(etat.date_iso),
                        int(etat.rang), code)
    etat.ouvert = False


def rendre_a_la_grille(etat: ModeGrille) -> None:
    retirer_exception(annee_regardee()["id"], str(etat.date_iso),
                      int(etat.rang))
    etat.ouvert = False


def revenir_en_arriere() -> None:
    if annuler_derniere_grille(annee_regardee()["id"]):
        ui.notification("Grille rendue telle qu'elle était",
                        variant="success", duration_ms=2000)
        return
    ui.notification("Aucune modification à annuler", variant="info",
                    duration_ms=2000)


def ouvrir_horaire(rang: int, debut: str, fin: str) -> None:
    draft = HoraireDraft()
    draft.rang = rang
    draft.debut = debut
    draft.fin = fin
    draft.ouvert = True


def enregistrer_horaire(draft: HoraireDraft) -> None:
    regler_horaire(annee_regardee()["id"], int(draft.rang),
                   str(draft.debut), str(draft.fin))
    draft.ouvert = False


# ── Le rendu ─────────────────────────────────────────────────────────

def cellule_bloc(bloc: dict, rangs: int, cible: int | None,
                 jour: str = "", changer: Callable[[], None] | None = None,
                 fige: bool = False, geste: tuple[str, str] = ("", "")) -> None:
    """Une case occupée : la classe, sa salle, son TP, sa pastille.

    **EF-B14 — la case mène à DEUX endroits** : la classe, et le cahier
    de texte avec la classe ET la date. *« C'est le chemin le plus court
    entre "qu'ai-je fait lundi ?" et la réponse. »*

    ⚠️ **Ce sont deux LIENS dans une carte ordinaire, et surtout pas une
    carte-lien qui en contient un second.** La première version faisait
    ça — ``ui.card(href=…)`` avec un ``ui.link`` dedans — et le résultat
    était cassé d'une façon qu'aucun test ne voyait : HTML interdit un
    ``<a>`` dans un ``<a>``, donc le parseur du navigateur FERME le lien
    extérieur en rencontrant l'intérieur, et tout ce qui suit sort de la
    carte. Mesuré : la carte rendait 130 px de vide, et le nom de la
    salle s'affichait dessous, dans la case de l'heure suivante. Le HTML
    sérialisé était pourtant juste — c'est le parseur qui le réécrit.
    """
    # Un liseré de 2 px et pas de 4 : une grille de trente cases est
    # un MUR, et c'est l'ambre d'une nature ou le rouge d'un refus qui
    # doivent s'y voir — pas le cas ordinaire.
    teinte = TEINTES["nature"] if bloc["nature"] else (
        TEINTES["exception"] if bloc.get("exception") else TEINTES["cours"])
    # ⚠️ Plus de ``ui.card`` : son thème pose un contour sur les quatre
    # côtés, et trente contours dans une grille font un damier. Un
    # événement d'agenda est une SURFACE teintée que sa barre de gauche
    # identifie — c'est ce que font tous les calendriers qu'on ouvre
    # sans y penser. Le rattrapage aurait été un ``border-0`` posé en
    # ``classes=`` par-dessus le thème ; c'est un composant de MOINS,
    # pas une classe de plus.
    with ui.vstack(gap="none", classes=teinte, style=hauteur(rangs)):
        with ui.hstack(gap="sm", justify="between", align="center"):
            # Le code de la classe s'écrit PAREIL, lien ou pas : c'est
            # ``ui.text`` qui porte sa graisse, dans les deux branches.
            # ``ui.link`` n'a ni ``weight=`` ni ``size=``, et le
            # rattraper en ``classes=`` aurait fait dire la même chose
            # à deux vocabulaires — celui du composant d'un côté,
            # Tailwind de l'autre.
            if cible:
                with ui.link(href=f"/classe/{cible}", variant="hover"):
                    ui.text(bloc["code"], weight="semibold")
            else:
                ui.text(bloc["code"], weight="semibold")
            with ui.hstack(gap="sm", align="center"):
                if changer is not None:
                    # ⚠️ DANS la case, et pas en dessous. La version
                    # d'avant empilait la carte et un bouton « Changer »
                    # dans un cadre haut de `hauteur(rangs)` — donc un
                    # contenu plus haut que sa boîte : le bouton sortait
                    # par le bas, recouvrait la case suivante, et la
                    # carte rognait sa deuxième ligne. Vu à l'écran.
                    #
                    # Le poser ici a un second effet, plus important que
                    # le premier : la grille ne BOUGE PLUS en passant de
                    # la lecture à la modification. On édite ce qu'on
                    # regardait, à la même place.
                    mot, icone = geste
                    ui.icon_button(
                        icone, variant="ghost", size="sm",
                        aria_label=f"{mot} {bloc['code']}",
                        tooltip=f"{mot} {bloc['code']}",
                        disabled=fige, on_click=changer,
                    )
                if est_un_tp(bloc):
                    # EF-B10 : rien n'est saisi ni stocké — la règle
                    # se LIT dans la grille.
                    ui.badge(label="TP", color="primary", variant="soft",
                             size="lg")
                if bloc["consignee"]:
                    # EF-B13 : d'un coup d'œil sur la semaine, ce qui
                    # reste à écrire au cahier de texte.
                    ui.icon("book-check", color="success",
                            tooltip="Consignée au cahier de texte")
        with ui.hstack(gap="sm", align="center", wrap=True):
            if bloc["nature"]:
                ui.text(bloc["nature"], color="warning")
            if bloc["salles"]:
                ui.text(" · ".join(bloc["salles"]), color="muted")
            if cible and jour:
                ui.link(
                    label="cahier",
                    href=f"/cahier?classe={cible}&date={jour}",
                    variant="underline", color="muted",
                    tooltip="Le cahier de texte de ce jour-là",
                )


def case_vide(mode: str, rangs: int = 1) -> None:
    """Ce qui occupe la place d'une heure sans cours.

    En lecture, du vide. En modification, un cadre en pointillés : une
    case libre doit se voir comme une cible, sinon on ne sait pas où
    cliquer.
    """
    classes = ("rounded-lg border border-dashed border-text/15"
               if mode != "lecture" else "")
    ui.flex(classes=classes, style=hauteur(rangs))


def colonne_du_jour(jour: dict, index: int, bornes: dict, mode: str,
                    fige: bool, aujourdhui: date,
                    annee_id: int) -> None:
    """Une journée : son en-tête, puis ses cases de haut en bas.

    La colonne se lit en DEUX étages, et c'est ce qui la rend
    lisible : l'en-tête, puis un cadre qui porte la trame horizontale
    et toutes les cases. Le filet vit sur le cadre, donc il continue
    sous les blocs et à travers les heures creuses — une bordure posée
    sur les cases s'arrêterait là où il n'y a pas de case, c'est-à-dire
    exactement là où l'œil en a besoin.
    """
    vide_ce_jour = bool(jour["periode"]) and mode != "modification"
    dernier = max(bornes)
    with ui.vstack(gap="xs", classes="border-l border-text/10"):
        entete_de_jour(jour, aujourdhui)
        with ui.vstack(gap="xs", style=fond_de_colonne(dernier)):
            rang = 1
            while rang <= dernier:
                bloc = next(
                    (b for b in jour["blocs"] if b["debut"] == rang), None)
                if vide_ce_jour:
                    # Piège n° 12 : VIDE, pas grisé. On lirait quand même
                    # les cinq cours qu'on ne fera pas.
                    case_vide("lecture")
                    rang += 1
                    continue
                if bloc is None:
                    if mode == "lecture":
                        case_vide("lecture")
                    else:
                        bouton_de_case(jour, index, rang, mode, fige,
                                       occupee=False, saisie="")
                    rang += 1
                    continue
                rangs = bloc["fin"] - bloc["debut"] + 1
                if mode == "lecture":
                    # Le lien ne s'ouvre QU'EN LECTURE : en modification,
                    # un clic sur la case doit poser une classe, pas
                    # naviguer ailleurs.
                    cellule_bloc(
                        bloc, rangs, classe_id_de(annee_id, bloc["code"]),
                        jour["date"].isoformat())
                else:
                    cellule_bloc(
                        bloc, rangs, None, fige=fige,
                        geste=(("Annuler", "calendar-x")
                               if mode == "exceptions"
                               else ("Changer", "pencil")),
                        changer=partial(ouvrir_case, index, rang,
                                        jour["date"].isoformat(), True,
                                        bloc["code"]),
                    )
                rang = bloc["fin"] + 1


def entete_de_jour(jour: dict, aujourdhui: date) -> None:
    """La colonne porte la DATE RÉELLE, et le jour même est marqué.

    Hauteur FIXE : cf. :data:`HAUTEUR_ENTETE`. Un jour de vacances porte
    une ligne de plus, et sans cette contrainte il décalerait sa seule
    colonne d'un cran — le mardi en face de la mauvaise heure, la semaine
    de la Toussaint et pas les autres.
    """
    cest_aujourdhui = jour["date"] == aujourdhui
    with ui.vstack(
        gap="none", align="center", justify="center",
        style=f"height:{HAUTEUR_ENTETE}px",
        classes="border-b-2 " + (
            "border-primary" if cest_aujourdhui else "border-text/10"),
    ):
        ui.text(JOURS[jour["date"].weekday()].capitalize(),
                size="sm",
                weight="semibold" if cest_aujourdhui else None,
                color="primary" if cest_aujourdhui else None)
        if jour["periode"]:
            # EF-B4 : le nom de la période SOUS la date. Une colonne vide
            # sans explication se lit comme une panne.
            ui.text(jour["periode"], color="warning", truncate=True)
        else:
            # ⚠️ La DATE seule : ``jour_et_date`` rend « lun 07/09 »,
            # et la ligne du dessus dit déjà « Lundi ». Deux fois le
            # même mot dans un en-tête de trois centimètres.
            ui.text(jour["date"].strftime("%d/%m"),
                    size="sm", color="muted", classes="tabular-nums")


def bouton_de_case(jour: dict, index: int, rang: int, mode: str, fige: bool,
                   *, occupee: bool, saisie: str) -> None:
    if mode == "exceptions":
        # EF-B11 : la case occupée ne propose qu'une annulation, la case
        # libre qu'un ajout. Le libellé dit lequel des deux, et c'est la
        # seule chose qui les distingue à l'écran.
        libelle = "Annuler" if occupee else "Ajouter"
        icone = "calendar-x" if occupee else "calendar-plus"
    else:
        libelle = "Changer" if occupee else "Poser"
        icone = "pencil" if occupee else "plus"
    # ⚠️ ``ghost`` et ``muted`` pour une case LIBRE : une grille de
    # quarante cibles cerclées de la couleur d'accent crie plus fort que
    # les cinq cours qu'elle entoure. Dans un agenda, le vide est un
    # fond, pas un bouton — il devient une cible au survol et au clavier,
    # et le reste du temps il se tait.
    ui.button(
        libelle, variant="ghost", color="muted", icon_left=icone,
        disabled=fige,
        classes="w-full", style=hauteur(1) if not occupee else "",
        on_click=partial(ouvrir_case, index, rang,
                         jour["date"].isoformat(), occupee, saisie),
    )


def colonne_horaires(bornes: dict[int, tuple[str, str]], fige: bool) -> None:
    """La PREMIÈRE colonne, où se règlent les bornes (EF-B3)."""
    with ui.vstack(gap="xs"):
        with ui.vstack(gap="none", align="center", justify="center",
                       style=f"height:{HAUTEUR_ENTETE}px",
                       classes="border-b-2 border-text/10"):
            ui.text("Horaires", color="muted", weight="semibold",
                    size="sm")
        # La gouttière porte la MÊME trame que les jours : sans elle,
        # les heures flottent à côté d'une grille réglée, et c'est
        # justement l'alignement qu'on cherche à donner à l'œil.
        with ui.vstack(gap="xs", style=fond_de_colonne(max(bornes))):
            for rang in sorted(bornes):
                debut, fin = bornes[rang]
                # ⚠️ L'heure de DÉBUT seule, et posée en HAUT de sa
                # rangée. C'est la convention de tous les agendas, et
                # ce n'est pas un goût : une heure centrée dans sa
                # bande ne marque aucune frontière, donc l'œil ne sait
                # pas où un bloc de deux heures commence. La fin se lit
                # sur la ligne suivante ; celle du dernier créneau vit
                # dans le dialogue de réglage, qui porte les deux.
                ui.button(
                    debut, variant="ghost", disabled=fige, size="sm",
                    classes="w-full justify-end items-start pt-1 "
                            "whitespace-nowrap tabular-nums",
                    style=hauteur(1),
                    on_click=partial(ouvrir_horaire, rang, debut, fin),
                )


def barre_de_semaine(lundi: date, lettre: str | None, mode: str,
                     fige: bool) -> None:
    samedi = lundi + timedelta(days=5)
    with ui.hstack(gap="md", justify="between", align="center", wrap=True):
        with ui.hstack(gap="sm", align="center"):
            ui.icon_button("chevron-left", variant="outline",
                           aria_label="Semaine précédente",
                           on_click=partial(aller_a, -1))
            ui.button("Aujourd'hui", variant="ghost",
                      on_click=partial(aller_a, 0))
            ui.icon_button("chevron-right", variant="outline",
                           aria_label="Semaine suivante",
                           on_click=partial(aller_a, 1))
            ui.text(f"{jour_et_date(lundi)} — {jour_et_date(samedi)}",
                    weight="medium")
            # EF-B2 : la lettre se DÉDUIT de la semaine affichée et
            # s'affiche en tête. Elle ne se choisit pas — il n'y a donc
            # aucun contrôle ici, juste le résultat.
            if lettre:
                ui.badge(label=f"Semaine {lettre}", color="primary",
                         variant="solid", size="xl")
            else:
                ui.badge(label="semaine indéterminée", color="warning",
                         variant="soft", size="xl")
        with ui.hstack(gap="sm", align="center", wrap=True):
            for valeur, libelle, icone in MODES:
                ui.button(
                    libelle,
                    variant="solid" if mode == valeur else "outline",
                    icon_left=icone, disabled=fige and valeur != "lecture",
                    on_click=partial(changer_mode, valeur),
                )
            if mode == "modification":
                ui.button("Annuler la dernière modification",
                          variant="ghost", icon_left="undo-2", disabled=fige,
                          on_click=revenir_en_arriere)


# ``HoraireDraft`` n'est PAS dans cette liste : la grille ne le lit
# pas. Il y était pour rafraîchir ``dialogue_horaire``, qui était
# appelé ici — donc ouvrir les bornes d'un créneau redessinait la
# semaine entière.
@refreshable(deps=[AnneeVue, SemaineVue, ModeGrille])
def grille() -> None:
    annee = annee_regardee()
    etat = ModeGrille()
    lundi = lundi_affiche(annee, str(SemaineVue().lundi))
    semaine = semaine_affichee(annee, lundi)
    mode = str(etat.mode)
    fige = en_consultation()

    with ui.vstack(gap="md"):
        barre_de_semaine(lundi, semaine["lettre"], mode, fige)
        if not semaine["lettre"]:
            ui.banner(
                message="Aucune date de référence de semaine A : "
                        "l'alternance est indéterminée, donc la grille type "
                        "n'est pas lisible. À régler dans les Réglages.",
                icon="circle-help", color="warning",
                            size="lg",
            )
        with ui.grid(gap="xs", classes=COLONNES):
            colonne_horaires(semaine["bornes"], fige)
            for index, jour in enumerate(semaine["jours"]):
                colonne_du_jour(jour, index, semaine["bornes"], mode, fige,
                                date.today(), annee["id"])


@refreshable(deps=[ModeGrille])
def dialogue_de_case() -> None:
    etat = ModeGrille()
    if str(etat.mode) == "exceptions":
        dialogue_exception(etat)
        return
    with (
        ui.dialog(open=etat.ouvert, title="Poser une classe",
                  on_close=fermer_case),
        ui.form(on_submit=enregistrer_case),
        ui.vstack(gap="md"),
    ):
        ui.text(
            "Tapez le code de la classe. Un code inconnu la CRÉE, vide — "
            "l'emploi du temps arrive fin août, les listes d'élèves à la "
            "rentrée. Ce qui suit se lit comme une SALLE, sauf les mots de "
            "la liste des natures (HVC), qui retirent l'heure du cahier de "
            "texte. Laisser vide efface la case.",
            color="muted",
        )
        with ui.form_field(label="Classe, nature, salle",
                           hint="4e1 · 3e4 (L) · 2°GT2 - 134 · 4e2 - HVC"):
            ui.input(value=etat.saisie, placeholder="4e1 - L")
        with ui.hstack(justify="end"):
            ui.button("Poser", type="submit", color="primary")


def dialogue_exception(etat: ModeGrille) -> None:
    occupee = bool(etat.occupee)
    titre = "Annuler cette heure" if occupee else "Ajouter une heure"
    with ui.dialog(open=etat.ouvert, title=titre, on_close=fermer_case):
        if occupee:
            with ui.vstack(gap="md"):
                ui.text(
                    "Cette heure est déjà prise : on n'est pas à deux "
                    "endroits à la fois, donc la seule décision possible "
                    "est de l'annuler pour cette date.",
                    color="muted",
                )
                with ui.hstack(gap="md", justify="between"):
                    ui.button("Rendre à la grille type", variant="ghost",
                              on_click=rendre_a_la_grille)
                    ui.button("Annuler cette heure", color="error",
                              icon_left="calendar-x", on_click=annuler_lheure)
            return
        with ui.form(on_submit=ajouter_lheure), ui.vstack(gap="md"):
            ui.text(
                "Cette case est libre : il n'y a rien à y annuler, "
                "seulement une heure à y ajouter, pour cette date.",
                color="muted",
            )
            with ui.form_field(label="Classe"):
                ui.input(value=etat.saisie, placeholder="4e1")
            with ui.hstack(gap="md", justify="between"):
                ui.button("Rendre à la grille type", variant="ghost",
                          on_click=rendre_a_la_grille)
                ui.button("Ajouter", type="submit", color="primary")


@refreshable(deps=[HoraireDraft])
def dialogue_horaire() -> None:
    draft = HoraireDraft()
    with (
        ui.dialog(open=draft.ouvert, title="Bornes de ce créneau"),
        ui.form(on_submit=enregistrer_horaire),
        ui.vstack(gap="md"),
    ):
        ui.text("Réglé pour toute l'année, sur les six jours.", color="muted")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            with ui.form_field(label="Début"):
                ui.time_picker(value=draft.debut)
            with ui.form_field(label="Fin"):
                ui.time_picker(value=draft.fin)
        with ui.hstack(justify="end"):
            ui.button("Enregistrer", type="submit", color="primary")


@page(PATH, layout=shell, title="Emploi du temps")
def emploi_du_temps_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Emploi du temps", level=1, size="2xl")
        # EF-B15 : les cadres d'entrée en cours, EN TÊTE de la
        # grille. Ce n'est pas le bandeau « Maintenant » d'EF-B16 :
        # celui-là répétait ce que la grille dit en mieux, celui-ci
        # porte ce qu'on ne peut lire nulle part ailleurs — la
        # dernière séance faite et le travail à vérifier.
        cadres_du_jour()
        grille()
    # Montés par la PAGE : une zone appelée dans une autre repart avec
    # elle, et ces deux dialogues sont fermés presque tout le temps.
    dialogue_de_case()
    dialogue_horaire()


feature = Feature(
    name="emploi_du_temps",
    kind="page",
    provides=[emploi_du_temps_page, SemaineVue, ModeGrille, HoraireDraft],
    uses=["grille_data", "annees", "shell", "suivi"],
)
