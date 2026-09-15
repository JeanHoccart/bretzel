"""features/annees — l'année qu'on regarde, et la barrière RT-1.

``kind="logic"`` : la feature la plus courte de l'app, et celle que
toutes les autres liront. Elle répond à deux questions, et l'application
entière dépend de la seconde.

1. **Quelle année regarde-t-on ?** Un choix de confort, rangé dans la
   session — il survit à une navigation, il ne suit personne d'un poste à
   l'autre, et il n'est **pas** dans l'adresse. EF-U1 énumère ce que
   l'adresse doit porter — la classe, le trimestre, l'onglet, la semaine,
   la salle, le tri — et l'année n'y est pas : ce n'est pas *ce qu'on
   regarde*, c'est *depuis quand on regarde*.

2. **A-t-on le droit d'écrire ?** C'est RT-1, et c'est une RÈGLE, pas un
   écran : *« une saisie faite par erreur dans l'année d'avant passerait
   sinon inaperçue »*. La garde est donc une fonction que chaque écriture
   appelle, et le bouton qu'on n'affiche pas (EF-C10) n'est que la
   politesse par-dessus.

⚠️ **Pourquoi la garde n'est pas dans ``db.execute``.** Elle ne pourrait
pas : l'année concernée dépend de la table, et parfois d'une jointure —
une place de plan appartient à une salle, qui appartient à une classe,
qui appartient à une année. Une garde posée à la porte SQL devrait
redécouvrir cette chaîne pour chaque écriture, ou se taire. Ici elle
prend l'année en paramètre : c'est plus verbeux, et c'est le point — on
peut RELIRE une fonction d'écriture et voir si elle est gardée.
"""

from __future__ import annotations

from functools import partial

from bretzel import Feature, ui
from bretzel.state import SessionState, field
from examples.ecole.core.db import query


class AnneeEnConsultationError(RuntimeError):
    """Une écriture a visé une année qui n'est pas celle en cours (RT-1).

    Une vraie levée plutôt qu'un retour ``False`` : un refus qu'on peut
    ignorer en oubliant de lire la valeur de retour n'est pas une
    barrière. L'app la rattrape là où elle sait quoi dire à l'écran ;
    ailleurs, elle remonte, et une page d'erreur vaut mieux qu'une
    écriture silencieuse dans l'année d'avant.
    """


class AnneeVue(SessionState):
    """L'année que CE navigateur regarde. Vide = celle en cours.

    ⚠️ **Le vide est une valeur, pas un trou.** Un identifiant par défaut
    serait faux le jour où la base change d'année — et un état de session
    ne peut pas lire la base pour se donner un défaut. ``""`` veut dire
    « celle qui est en cours, quelle qu'elle soit », ce qui reste vrai
    après la bascule d'une rentrée à l'autre.
    """

    annee: str = field(default="")


def toutes_les_annees() -> list[dict]:
    """Les années, la plus récente d'abord."""
    return query(
        "SELECT id, libelle, debut, fin, en_cours, lundi_ref "
        "FROM annees ORDER BY debut DESC"
    )


def annees_regardee_et_en_cours() -> tuple[dict, dict]:
    """Les DEUX années qui décident de tout, en **une seule lecture**.

    Elles sortent de la même liste, et les demander séparément la
    relisait deux fois. Mesuré le 2026-09-13 sur ``/plan/1`` : vider une
    place partait sur **9 lectures de la table des années** pour 26
    requêtes SQL au total, parce que quatre zones appelaient chacune un
    :func:`en_consultation` qui en coûtait deux.

    S'il n'y avait aucune année en cours — une base à moitié semée — la
    plus récente fait office : un écran vide serait une panne de plus à
    diagnostiquer, alors qu'une année qui refuse l'écriture se voit à
    l'écran. Et un choix qui ne désigne plus rien (une année supprimée,
    une session qui traîne) retombe sur l'année en cours plutôt que de
    lever : un réglage périmé ne doit pas bloquer une page.
    """
    annees = toutes_les_annees()
    en_cours = next((a for a in annees if a["en_cours"]), annees[0])
    choisie = str(AnneeVue().annee)
    if choisie:
        for annee in annees:
            if str(annee["id"]) == choisie:
                return annee, en_cours
    return en_cours, en_cours


def annee_en_cours() -> dict:
    """L'année dans laquelle on a le droit d'écrire (RT-1).

    Une seule année est en cours à la fois (§ 5.1).
    """
    return annees_regardee_et_en_cours()[1]


def annee_regardee() -> dict:
    """L'année que l'écran doit montrer — choisie, ou celle en cours."""
    return annees_regardee_et_en_cours()[0]


def en_consultation() -> bool:
    """Regarde-t-on une année qu'on n'a pas le droit d'écrire ?"""
    regardee, en_cours = annees_regardee_et_en_cours()
    return regardee["id"] != en_cours["id"]


def garde_ecriture(annee_id: int) -> None:
    """**La barrière RT-1.** Lève si ``annee_id`` n'est pas l'année en cours.

    À appeler en PREMIÈRE ligne de toute fonction qui écrit une donnée
    datée. Elle prend l'identifiant de l'année visée, jamais celui de
    l'année regardée : une écriture peut viser autre chose que ce que
    l'écran affiche, et c'est justement le cas qu'on veut attraper.
    """
    en_cours = annee_en_cours()
    if annee_id != en_cours["id"]:
        raise AnneeEnConsultationError(
            f"Écriture refusée : l'année visée (#{annee_id}) n'est pas "
            f"l'année en cours ({en_cours['libelle']}). Les autres années "
            f"se consultent entièrement et n'acceptent aucune écriture "
            f"(RT-1)."
        )


def options_annees() -> list[tuple[str, str]]:
    """Les choix du sélecteur. ``""`` = l'année en cours, nommée.

    La première entrée porte le LIBELLÉ de l'année en cours et pas le mot
    « en cours » tout seul : le sélecteur doit dire quelle année on
    regarde, pas quel réglage est actif.
    """
    annees = toutes_les_annees()
    en_cours = next((a for a in annees if a["en_cours"]), annees[0])
    return [
        ("", f"{en_cours['libelle']} · en cours"),
        *(
            (str(a["id"]), a["libelle"])
            for a in annees
            if a["id"] != en_cours["id"]
        ),
    ]


def changer_annee(vue: AnneeVue) -> None:
    """Le professeur change d'année ; les zones ``deps=`` se re-rendent.

    ⚠️ Le corps est vide **et c'est le mécanisme** : le socle a déjà
    hydraté ``vue.annee`` avant d'appeler le handler, et la mutation
    seule déclenche le re-render des zones qui déclarent
    ``deps=[AnneeVue]``. Le paramètre TYPÉ est ce qui hydrate — un
    handler sans lui répondrait zéro octet.
    """


def aller_a_lannee(valeur: str) -> None:
    """Regarder une autre année. ``""`` = celle en cours.

    Le corps mute l'état et rien d'autre : les zones qui déclarent
    ``deps=[AnneeVue]`` se re-rendent toutes seules.
    """
    AnneeVue().annee = valeur


def selecteur_annee() -> None:
    """Les années, en entrées du PIED de la barre latérale (EF-U2).

    Elles vivent dans la coque et pas dans une page : le choix porte sur
    TOUS les écrans, donc il appartient au cadre.

    ⚠️ **Dans le pied, et pas en section.** La version d'avant posait un
    ``ui.select`` dans le corps de la barre. Replié en rail, le champ
    était écrasé à la largeur du rail : une boîte de deux centimètres
    avec un chevron et rien d'autre. C'est un défaut que l'utilisateur a
    signalé deux fois, et qu'aucune app ne peut réparer chez elle — le
    repli est un état CLIENT, donc un écran rendu par le serveur ne sait
    pas qu'il est dedans.

    ``ui.sidebar_footer``, lui, le sait : en rail il ne montre que
    l'avatar, et son menu flotte AU-DESSUS de la barre (il passe en
    ``position: fixed`` pour échapper à son ``overflow``). C'est la
    réponse que le framework donne déjà, et elle n'était pas utilisée.
    """
    courante = AnneeVue().annee
    for valeur, libelle in options_annees():
        ui.sidebar_footer_item(
            label=libelle,
            icon_left="check" if valeur == courante else "calendar",
            on_click=partial(aller_a_lannee, valeur),
        )


def bandeau_consultation() -> None:
    """« Année en consultation » — sur CHAQUE écran qui refuserait une
    écriture (EF-U2).

    Rendu dans la coque, donc il n'y a aucun écran où l'oublier. Le texte
    dit ce qui est interdit, pas seulement ce qui est vrai : « lecture
    seule » se lit comme un état, « aucune saisie n'est possible » comme
    une conséquence.
    """
    if not en_consultation():
        return
    ui.banner(
        message=f"{annee_regardee()['libelle']} — année en consultation. "
                f"Aucune saisie n'est possible ; seule "
                f"{annee_en_cours()['libelle']} s'écrit.",
        icon="eye",
        color="warning",
            size="lg",
    )


feature = Feature(
    name="annees",
    kind="logic",
    provides=[
        AnneeVue, AnneeEnConsultationError, toutes_les_annees,
        annees_regardee_et_en_cours, annee_en_cours,
        annee_regardee, en_consultation, garde_ecriture, options_annees,
        changer_annee, selecteur_annee, bandeau_consultation,
    ],
    uses=["db"],
)
