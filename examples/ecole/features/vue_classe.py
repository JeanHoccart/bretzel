"""features/vue_classe — state : ce qu'on regarde d'une classe.

``kind="state"`` : une feature qui ne porte qu'un état typé, et qui
existe pour une raison précise — **casser un cycle de contrat**.

Comment elle est née
--------------------
L'écran de classe (``features/classe.py``) monte ses onglets, et chaque
onglet est une feature à part : ``evaluations`` au lot 5, le bilan au 6,
le plan au 7. Les deux côtés ont besoin de la même chose — quelle classe,
quel trimestre — donc le premier jet a mis ``VueClasse`` dans
``classe.py`` et fait importer le panneau depuis là. Résultat :
``classe`` importe ``evaluations`` qui importe ``classe``.

``bretzel check --deep`` l'a dit en trois lignes (*« la feature `classe`
importe ['evaluations'] sans le déclarer »*), et déclarer le ``uses`` des
deux côtés aurait fermé le cycle dans le CONTRAT au lieu de le retirer du
code — c'est-à-dire écrit noir sur blanc qu'on l'assume.

L'état partagé dans sa propre feature coûte dix lignes et rend le graphe
acyclique : ``classe`` et ``evaluations`` en dépendent tous les deux,
aucun ne dépend de l'autre. C'est aussi ce qui a permis de retirer
l'unique import différé de l'app.
"""

from __future__ import annotations

from bretzel import Feature, refreshable, ui
from bretzel.state import PageState, field


class VueClasse(PageState, addressable=True):
    """La classe ouverte et le trimestre regardé.

    ⚠️ **``classe_id`` vit ici et pas dans la signature des zones**, et
    c'est le socle qui l'impose : une zone ``@refreshable`` est rappelée
    SANS argument au rafraîchissement. Un paramètre obligatoire lève un
    500 à la première action qui touche un ``deps`` — jamais au
    chargement, donc jamais en relisant la page ; un paramètre à valeur
    par défaut ne lève rien et re-rend simplement une AUTRE classe.

    Seul ``trimestre`` porte un ``url=`` : la classe est dans le CHEMIN,
    c'est un identifiant de ressource et pas un réglage de vue (EF-U1).
    """

    classe_id: int = field(default=0)
    trimestre: int = field(default=1, url="t")


def changer_trimestre(vue: VueClasse) -> None:
    """Le corps est vide **et c'est le mécanisme** : le socle a hydraté
    ``vue.trimestre`` avant l'appel, et la mutation seule re-rend les
    zones qui déclarent ``deps=[VueClasse]``. Le paramètre TYPÉ est ce
    qui hydrate — sans lui, le handler répondrait zéro octet."""


@refreshable(deps=[VueClasse])
def selecteur_trimestre() -> None:
    """Le trimestre regardé (EF-C2), et il vit dans l'adresse (EF-U1).

    Une zone à lui seul : il commande TOUS les panneaux de l'écran — les
    élèves, les évaluations, le bilan — donc il ne peut vivre dans aucun
    d'eux.
    """
    vue = VueClasse()
    with ui.hstack(gap="md", align="center", wrap=True):
        ui.text("Trimestre", color="muted")
        ui.toggle_group(
            value=vue.trimestre,
            options=[(1, "1"), (2, "2"), (3, "3")],
            on_change=changer_trimestre,
        )


feature = Feature(
    name="vue_classe",
    kind="state",
    provides=[VueClasse, changer_trimestre, selecteur_trimestre],
)
