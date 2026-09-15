"""Gate : les deux chapitres de RÉFÉRENCE ne peuvent pas prendre du retard.

Ce qu'elle garde, et pourquoi elle existe
------------------------------------------
``examples/docs`` est la doc vivante. Deux chapitres avaient pourtant
dérivé sans que rien ne le dise, et il a fallu que quelqu'un le remarque
à l'œil :

- **Thème** documentait **3 des 12 paramètres** de :class:`Theme`. Les
  neuf autres — le mode sombre, les rayons, le trait, les fontes, la
  feuille CSS de l'app, la barre de défilement, les icônes, le thème de
  base — étaient livrés et invisibles.
- **Structure d'app** annonçait « les trois rôles de feature » et en
  nommait trois, alors qu'il y en a onze ; et ne mentionnait nulle part
  :class:`~bretzel.Feature`, le contrat vérifié en graphe au démarrage.

Le remède n'est pas de les réécrire — c'est de rendre l'écart VISIBLE :

1. la table des paramètres du thème se construit sur
   ``inspect.signature(Theme)``, et cette gate exige qu'une phrase
   existe pour chacun ;
2. la table des marqueurs RÉSOUT chaque symbole qu'elle nomme, et cette
   gate exige que tous résolvent.

Un paramètre ajouté à ``Theme`` demain, ou un décorateur renommé, fait
donc rougir ici — pas six mois plus tard, sur une capture d'écran.
"""

from __future__ import annotations

import inspect

from bretzel.theme import Theme

from examples.docs.features.structure import MARQUEURS, resolve
from examples.docs.features.theme import ROLES, THEME_PARAMS

#: Preuve de morsure : contrôle POSITIF — le résolveur de la page sait
#: dire oui à un vrai symbole ET non à un faux.
MUTATION_PROOF = "test_the_resolver_of_the_page_is_not_blind"

#: Le compte au gel. Planchers, pas plafonds — les deux listes doivent
#: pouvoir grandir. Ils sont là pour qu'une table vidée ne rende pas les
#: exigences vertes en ne regardant rien.
_THEME_PARAMS_AT_FREEZE = 12
_MARQUEURS_AT_FREEZE = 11


def test_the_resolver_of_the_page_is_not_blind() -> None:
    """Plancher, ancré sur la DÉCOUVERTE des deux chapitres.

    Sans lui, un ``resolve`` qui rendrait toujours ``True``, ou des
    tables vides, feraient passer les deux exigences en ne vérifiant
    rien.
    """
    assert len(THEME_PARAMS) >= _THEME_PARAMS_AT_FREEZE, (
        f"{len(THEME_PARAMS)} paramètres lus sur `Theme` contre "
        f"{_THEME_PARAMS_AT_FREEZE} au gel — la lecture de signature est "
        f"probablement cassée."
    )
    assert len(MARQUEURS) >= _MARQUEURS_AT_FREEZE, (
        f"{len(MARQUEURS)} marqueurs listés contre "
        f"{_MARQUEURS_AT_FREEZE} au gel — la table a rétréci."
    )
    # …et le résolveur doit trancher DANS LES DEUX SENS. Le versant
    # licite est celui qui attrape un résolveur trop permissif, et c'est
    # le plus utile : un `return True` passerait toutes les exigences.
    assert resolve("bretzel.page"), "un vrai symbole doit résoudre"
    assert resolve("bretzel.auth"), "un MODULE doit résoudre aussi"
    assert not resolve("bretzel.ce_decorateur_n_existe_pas")
    assert not resolve("paquet.qui.n.existe.pas")


def test_the_theme_chapter_covers_every_theme_parameter() -> None:
    """Chaque levier de ``Theme`` a sa phrase dans le chapitre.

    La signature dit le NOM et le TYPE ; elle ne dit jamais à quoi ça
    sert. La table de la page marie les deux, et c'est le mariage qui
    peut se défaire — d'où la vérification des deux sens.
    """
    reels = set(inspect.signature(Theme).parameters)
    sans_phrase = sorted(reels - set(ROLES))
    assert not sans_phrase, (
        f"paramètre(s) de `Theme` sans explication dans le chapitre "
        f"Thème : {sans_phrase}.\n"
        f"  Ajoute une phrase dans `ROLES` "
        f"(examples/docs/features/theme.py) — un levier livré et non "
        f"documenté est exactement ce qui avait laissé 9 paramètres sur "
        f"12 invisibles."
    )
    orphelines = sorted(set(ROLES) - reels)
    assert not orphelines, (
        f"le chapitre Thème explique {orphelines}, que `Theme` n'accepte "
        f"pas (ou plus). Retire la phrase, ou corrige le nom."
    )


def test_the_structure_chapter_names_real_decorators() -> None:
    """Les onze marqueurs annoncés existent tous."""
    fantomes = sorted(
        chemin for chemin, _, _ in MARQUEURS if not resolve(chemin)
    )
    assert not fantomes, (
        f"le chapitre Structure d'app nomme {fantomes}, qui ne "
        f"résout(ent) pas.\n"
        f"  La page l'affiche déjà en clair (« introuvable — cette page "
        f"est périmée »), mais personne ne relit une page tous les "
        f"jours : corrige `MARQUEURS` "
        f"(examples/docs/features/structure.py)."
    )


def test_a_marker_is_listed_once() -> None:
    """Aucun décorateur n'est annoncé deux fois sous deux formes.

    Le cas se produit en ajoutant une ligne sans relire la table — et
    deux lignes pour un même symbole donnent l'impression de deux
    mécanismes là où il n'y en a qu'un.
    """
    chemins = [chemin for chemin, _, _ in MARQUEURS]
    doublons = sorted({c for c in chemins if chemins.count(c) > 1})
    assert not doublons, f"marqueur(s) listé(s) deux fois : {doublons}."
