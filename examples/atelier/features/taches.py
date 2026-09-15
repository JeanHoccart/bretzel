"""features/taches — page : le RYTHME, une ligne par tâche.

C'est l'écran qui répond à la question posée : « où est-ce que je plante,
où est-ce que je suis lent, pourquoi pas du premier coup ». Chaque ligne
est une tâche — un message de l'utilisateur jusqu'à la réponse finale —
et porte sa frise, ses cycles de vérification, ses erreurs.

La colonne qui décide est **cycles** : la règle posée est « on code tout,
on vérifie, on corrige, on vérifie une dernière fois ». Deux cycles, pas
plus. Trois veut dire qu'on a recommencé ; dix, qu'on s'est servi de la
suite de tests comme d'un compilateur.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.state import field
from examples.atelier.core.epoque import LIBELLE as LIBELLE_EPOQUE
from examples.atelier.core.epoque import POURQUOI as POURQUOI_EPOQUE
from examples.atelier.core.perimetre import short
from examples.atelier.core.phases import (
    COULEUR_PAR_LETTRE,
    CYCLES_MAX,
    LETTRES,
    LIBELLES,
)
from examples.atelier.features.shell import shell
from examples.atelier.features.taches_data import (
    VERDICTS,
    load_taches,
    perimetres_connus,
    resume,
)


class TachesTable(DatatableState, scope="session", addressable=True):
    """La requête de CETTE table.

    ``addressable=True`` : trier ou chercher réécrit l'adresse, donc une
    vue se partage. Pointer une tâche précise à quelqu'un est exactement
    l'usage de cet écran.
    """

    per_page: int = field(default=25)
    sort_key: str = field(default="debut")
    sort_dir: str = field(default="desc")


def cycles_cell(value, _row):
    """Le nombre de cycles, peint par la règle plutôt que par un seuil rond."""
    couleur = "success" if value <= CYCLES_MAX else "error"
    return ui.badge(str(value), color=couleur, variant="soft", size="xs")


def verdict_cell(value, _row):
    couleurs = {
        "du premier coup": "success",
        "corrigé": "warning",
        "aller-retour": "error",
    }
    return ui.badge(value, color=couleurs.get(value, "muted"),
                    variant="soft", size="xs")


#: Au-delà, la frise est TRONQUÉE dans la liste. Mesuré : une tâche de
#: 43 cycles rend une frise de 90 lettres qui se replie sur vingt lignes
#: et fait une rangée de 201 px — la table devient un mur et cesse de se
#: comparer d'un coup d'œil, qui est tout ce qu'on lui demande. Le
#: déroulé complet vit sur la fiche de la tâche.
#: Mesuré : à 28 la colonne pesait 223 px et la table débordait encore de
#: 47 px de son hôte — donc une barre horizontale, celle-là même qu'on
#: vient de retirer ailleurs. À 20, la table TIENT.
FRISE_MAX = 20

#: La demande, coupée. Même défaut que la frise, et il était sous mes
#: yeux : 300 caractères se replient sur huit lignes et font une rangée
#: de 130 px. C'est la colonne la plus large de l'écran, donc c'est elle
#: qui décide si la table se compare d'un coup d'œil ou pas.
DEMANDE_MAX = 90


def frise_cell(value, _row):
    """La frise, chaque lettre PEINTE par sa phase.

    ⚠️ La couleur n'est pas de la décoration : c'est ce qui rend la
    colonne lisible SANS aller chercher la légende. L'utilisateur a dû
    demander « les frise c'est quoi du coup ? » devant une suite de
    lettres nues — une colonne qu'on doit décoder ailleurs ne se lit pas.
    Peinte, la tâche qui fait du ping-pong se repère à son alternance
    bleu/orange sans qu'on lise un seul caractère.
    """
    texte = value or "—"
    coupee = texte[:FRISE_MAX].rstrip() if len(texte) > FRISE_MAX else texte
    with ui.hstack(gap="xs", align="center",
                   classes="font-mono text-xs whitespace-nowrap") as cellule:
        # Les espaces de la frise sautent : c'est le `gap` de la pile qui
        # sépare les lettres. Une espace rendue en composant demanderait
        # un primitive qui n'existe pas — vérifié plutôt que supposé.
        for lettre in coupee.replace(" ", ""):
            ui.text(lettre, size="xs", weight="bold",
                    color=COULEUR_PAR_LETTRE.get(lettre, "muted"))
        if len(texte) > FRISE_MAX:
            ui.text(" …", size="xs", color="muted")
    return cellule


def demande_cell(value, row):
    """La demande, sur UNE ligne — et c'est ELLE qui ouvre la fiche.

    ⚠️ Un lien, pas un clic de ligne. Les deux ouvrent la même fiche et
    ils ne naviguent pas pareil : ``on_item_click=`` poste une action,
    le handler appelle ``redirect()``, htmx reçoit ``HX-Redirect`` et
    fait un ``window.location``. Le document est donc DÉTRUIT et la
    coque repeinte, en deux requêtes — mesuré le 2026-09-12, un marqueur
    posé sur ``window`` avant le clic n'y survivait pas.

    Un ``<a>`` est intercepté par le ``hx-boost`` de la coque : une
    requête, seule la région change, la barre latérale ne bouge pas.
    C'est ce que dit la docstring de :func:`bretzel.redirect` — « pour
    un menu, une ligne cliquable, un fil d'Ariane, la navigation reste
    un ``ui.link`` » — et que je n'avais pas lue.
    """
    texte = (value or "—").replace("\n", " ").strip()
    coupee = (
        texte[:DEMANDE_MAX].rstrip() + " …" if len(texte) > DEMANDE_MAX else texte
    )
    # ⚠️ La contrainte vit sur la CELLULE, pas sur `ui.column(width=)`.
    # Mesuré : avec `width="24rem"` la colonne faisait quand même 662 px
    # et poussait Verdict et Frise hors de l'écran. La table est en
    # `table-layout: auto`, où un `<col width>` n'est qu'une SUGGESTION —
    # le contenu gagne. Un `max-w` + `truncate` sur le texte, lui,
    # contraint pour de vrai.
    return ui.link(coupee, href=f"/tache/{row['id']}", variant="hover",
                   classes="block max-w-[22rem] truncate text-sm",
                   tooltip=texte if coupee != texte else None)


#: Les mois, pour une date qu'un humain lit. L'horodatage ISO brut
#: (``2026-09-12T10:03:46.413Z``) se replie sur deux lignes et ne se
#: compare pas — or comparer est tout ce qu'on demande à cette colonne.
MOIS = ("janv", "févr", "mars", "avr", "mai", "juin",
        "juil", "août", "sept", "oct", "nov", "déc")


def debut_cell(value, _row):
    """``2026-09-12T10:03:46Z`` → ``12 sept 10:03``.

    Le tri, lui, reste sur la valeur BRUTE : c'est la colonne SQL qui
    ordonne, pas ce qu'on affiche.
    """
    brut = value or ""
    try:
        mois = MOIS[int(brut[5:7]) - 1]
        return ui.text(f"{int(brut[8:10])} {mois} {brut[11:16]}",
                       size="sm", classes="whitespace-nowrap")
    except (ValueError, IndexError):
        return ui.text(brut[:16], size="sm")


def perimetre_cell(value, _row):
    """Le périmètre, écrit pour être lu, et peint si c'est une app."""
    est_app = value.startswith("app:")
    return ui.badge(short(value), variant="soft", size="xs",
                    color="primary" if est_app else "muted")


def erreurs_cell(value, _row):
    if not value:
        return ui.text("—", size="sm", color="muted")
    return ui.badge(str(value), color="error", variant="soft", size="xs")


#: ⚠️ Huit colonnes tenaient mal dans 1 136 px : Verdict et Frise
#: sortaient de l'écran. `Erreurs` est partie — le verdict la RÉSUME
#: déjà (« corrigé » veut dire qu'il y en a eu), donc elle payait une
#: colonne pour redire une autre. La frise, elle, est ce qu'on vient
#: lire : elle reste.
COLUMNS = [
    ui.column("debut", label="Début", sortable=True, render=debut_cell),
    ui.column("perimetre", label="Périmètre", sortable=True,
              filter=perimetres_connus(), render=perimetre_cell),
    ui.column("demande", label="Demande", render=demande_cell),
    ui.column("minutes", label="Minutes", sortable=True, align="right"),
    ui.column("appels", label="Appels", sortable=True, align="right"),
    ui.column("cycles", label="Cycles", sortable=True, align="right",
              render=cycles_cell),
    ui.column("verdict", label="Verdict", sortable=True,
              filter=list(VERDICTS), render=verdict_cell),
    ui.column("frise", label="Frise", render=frise_cell),
]


def kpi(libelle: str, valeur: str, aide: str = "") -> None:
    """Un nombre et ce qu'il veut dire — le libellé seul ne suffit pas."""
    with ui.card(classes="flex-1 min-w-40"), ui.vstack(gap="xs"):
        ui.text(libelle, size="xs", color="muted")
        ui.text(valeur, size="2xl", weight="bold")
        if aide:
            ui.text(aide, size="xs", color="muted")


@page("/", title="Tâches", layout=shell)
def taches_page() -> None:
    """Le rythme, tâche par tâche."""
    apps = resume(apps_seulement=True)
    tout = resume()

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.heading("Le rythme", level=1)
        ui.text(
            "Une ligne par tâche : ce que tu as demandé, jusqu'à ma réponse. "
            f"La règle est de {CYCLES_MAX} cycles de vérification au plus — "
            "on code tout, on vérifie, on corrige, on vérifie une dernière "
            "fois. Au-delà, c'est du tâtonnement.",
            color="muted",
        )
        # ⚠️ Le jalon est DIT, pas seulement appliqué. Une app qui montre
        # 67 tâches sur 1 525 sans expliquer pourquoi ment par omission —
        # et c'est précisément en ne comprenant pas d'où sortaient des
        # lignes que l'utilisateur a ouvert cette question.
        ui.text(
            f"Lecture {LIBELLE_EPOQUE} — {POURQUOI_EPOQUE}. "
            "Les tâches d'avant sont aspirées mais pas comptées : elles "
            "n'ont pas pu suivre une règle dont les outils n'existaient "
            "pas encore.",
            size="sm", color="muted",
        )

        # ⚠️ Les APPS d'abord, et seules en grand. C'est la question
        # posée : bâtir le socle demande de le lire en entier et de le
        # vérifier souvent — du travail sain qui ressemble à de
        # l'aller-retour. Mélanger les deux rend le chiffre faux dans les
        # deux sens.
        ui.text("Sur les applications", size="sm", weight="medium")
        with ui.hstack(gap="md", wrap=True):
            kpi("Tâches d'app", str(apps["taches"]),
                f"sur {tout['taches']} au total")
            kpi("Du premier coup", f"{apps['part_premier_coup']} %",
                f"contre {tout['part_premier_coup']} % tous périmètres")
            kpi("Cycles moyens", str(apps["cycles_moyens"]),
                f"la règle en autorise {CYCLES_MAX}")
            kpi("Lu avant d'écrire", f"{apps['lu_avant']} %",
                "le temps 1 de la règle")

        # ⚠️ Les trois gestes de méthode en PROSE et pas en cartes. Sept
        # cartes poussaient la table sous la ligne de flottaison, et la
        # table est ce qu'on vient lire. Un nombre qu'on compare mérite
        # une carte ; un nombre qu'on constate tient dans une phrase.
        # La LÉGENDE, sur l'écran où la frise se lit. Elle vivait
        # uniquement sur la fiche d'une tâche — donc trop tard.
        with ui.hstack(gap="md", align="center", wrap=True):
            ui.text("La frise", size="xs", weight="medium")
            for phase, lettre in LETTRES.items():
                with ui.hstack(gap="xs", align="center"):
                    ui.text(lettre, size="xs", weight="bold",
                            color=COULEUR_PAR_LETTRE[lettre],
                            classes="font-mono")
                    ui.text(LIBELLES[phase], size="xs", color="muted")

        ui.text(
            f"Sur ces mêmes tâches : `describe` consulté avant d'écrire "
            f"dans {apps['surface']} % des cas, `check --deep` dans "
            f"{apps['contrat']} %, pour {apps['appels']} appels d'outil "
            f"dont {apps['erreurs']} en échec.",
            size="sm", color="muted",
        )

        table()


@refreshable(deps=[TachesTable])
def table() -> None:
    """La table, DANS une zone qui surveille sa requête.

    ⚠️ **Pas de ``ui.pane`` autour.** La coque en pose déjà un, et deux
    régions à ``overflow-y-auto`` imbriquées font DEUX barres de
    défilement — dont une minuscule, parce que l'intérieure ne dépasse
    que de deux pixels. Mesuré ici : 1024×700 pour 4 028 de contenu à
    l'extérieur, 976×3682 pour 3 684 à l'intérieur. C'est le défaut que
    l'utilisateur a vu à l'écran avant moi.

    ⚠️ Ce n'est pas une précaution de style : trier, paginer et chercher
    marchent tous en MUTANT ``TachesTable``. Sans zone qui la déclare en
    ``deps=``, les contrôles posteraient et l'écran ne bougerait jamais —
    le framework refuse donc le montage au rendu plutôt que de livrer ce
    silence.
    """
    ui.datatable(
                state=TachesTable,
                columns=COLUMNS,
                rows=load_taches,
                search=True,
                search_placeholder="Chercher dans les demandes…",
                row_key="id",
                empty_text="Rien à regarder.",
                empty_description=(
                    "La base est vide : lance "
                    "`py -m examples.atelier.core.ingest`."
                ),
            )


feature = Feature(
    name="taches",
    kind="page",
    uses=["taches_data", "shell", "phases", "perimetre", "epoque"],
    provides=[taches_page],
)
