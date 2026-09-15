"""Gate : `describe X --theme` répond aux TROIS questions qu'on se pose.

Ce qu'elle ferme
----------------
La fiche normale nommait les clés et s'arrêtait juste avant la question
qu'on se pose en écrivant un ``Theme(components={…})``. Mesuré le
2026-09-10 en construisant le preset du kanban : **une dizaine de
``theme.py`` ouverts à la main** pendant que ``describe`` tournait, parce
qu'il rendait DEUX LIGNES IDENTIQUES pour ``button`` et pour ``select``
alors que les deux formes sont incompatibles.

Les trois manques, et ce que chacun coûte :

1. la **FORME** (chaîne ou dict de sous-clés) décide si la surcharge est
   LUE — un dict là où le thème livre une chaîne fait perdre tous les
   jetons du palier, le composant rend nu en 200 sans erreur ;
2. la **valeur courante** — sans elle on ne sait pas ce qu'on remplace ;
3. les **sous-clés d'un palier** : ``icon_pad_left`` vit DANS un palier de
   ``sizes`` sans être un slot, et n'apparaissait sur aucune liste. C'est
   la sous-clé exacte sur laquelle l'auteur s'est trompé.

Pourquoi une gate et pas seulement un test de format
-----------------------------------------------------
Une fiche qui se contenterait d'imprimer des noms repasserait un test qui
vérifie qu'elle rend du texte. Ce qui se garde ici, ce sont les trois
RÉPONSES — sur des composants choisis parce qu'ils se distinguent :
``button`` livre des paliers en chaîne, ``select`` et ``input`` en dict.
Si la fiche redevenait identique pour les deux, elle aurait reperdu ce
pour quoi elle a été écrite.
"""

from __future__ import annotations

import pytest

from bretzel.introspect import theme_sheet

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_two_incompatible_shapes_do_not_read_alike``.
MUTATION_PROOF = "test_two_incompatible_shapes_do_not_read_alike"


def test_the_shape_is_stated() -> None:
    """① La forme, pour les deux familles."""
    assert "forme « str »" in theme_sheet("button"), (
        "la fiche de `button` ne dit pas que ses paliers sont des CHAÎNES "
        "— c'est la moitié de ce qui décide si une surcharge est lue."
    )
    assert "forme « dict »" in theme_sheet("select"), (
        "la fiche de `select` ne dit pas que ses paliers sont des DICTS."
    )


def test_the_current_value_is_shown() -> None:
    """② La valeur du palier par défaut, en entier."""
    sheet = theme_sheet("button")
    assert "le défaut de size=" in sheet, (
        "la fiche ne désigne plus le palier que le composant prend sans "
        f"qu'on lui demande :\n{sheet}"
    )
    assert "h-10 px-4" in sheet, (
        "la fiche ne montre plus ce que vaut ce palier — sans la valeur, "
        f"on ne sait pas ce qu'on remplace :\n{sheet}"
    )


def test_the_sub_keys_of_a_step_are_shown() -> None:
    """③ Les sous-clés — le manque qui a coûté l'erreur d'origine."""
    sheet = theme_sheet("input")
    assert "icon_pad_left" in sheet, (
        "`icon_pad_left` n'apparaît pas. Il vit DANS un palier de `sizes` "
        "sans être un slot, il n'était sur aucune liste, et c'est la "
        f"sous-clé exacte sur laquelle l'auteur s'est trompé :\n{sheet}"
    )


def test_two_incompatible_shapes_do_not_read_alike() -> None:
    """Le versant qui a motivé la fiche : deux formes, deux lectures.

    C'est l'assertion qui rougirait si la fiche redevenait un catalogue
    de noms — l'état d'où l'on vient, où `button` et `select` rendaient
    exactement les mêmes deux lignes.
    """
    chaine = theme_sheet("button")
    dictionnaire = theme_sheet("select")

    assert chaine != dictionnaire
    assert "forme « str »" in chaine and "forme « str »" not in (
        dictionnaire.split("sizes")[-1]
    ), (
        "les deux fiches décrivent leurs paliers de `sizes` de la même "
        "façon, alors que l'une livre une chaîne et l'autre un dict. "
        "C'est exactement l'ambiguïté qui a fait ouvrir une dizaine de "
        "`theme.py` à la main."
    )


def test_a_sheet_stays_readable() -> None:
    """Elle ne vomit pas la table — sinon elle ne répond plus.

    `select` a 18 slots et `datatable` bien plus ; le catalogue porte
    70 855 caractères de classes. La fiche montre UN palier et nomme les
    autres, donc elle reste courte quel que soit le composant.
    """
    for name in ("select", "datatable", "input", "button"):
        lines = theme_sheet(name).splitlines()
        assert len(lines) <= 60, (
            f"la fiche de `{name}` fait {len(lines)} lignes — au-delà elle "
            "cesse d'être lue, donc de répondre. Montre UN palier et nomme "
            "les autres."
        )


@pytest.mark.parametrize("name", ["page", "zzz_inconnu"])
def test_a_non_component_is_refused_with_a_sentence(name: str) -> None:
    """Un nom qui n'est pas un composant ne rend pas une fiche vide."""
    with pytest.raises(KeyError) as caught:
        theme_sheet(name)
    assert name in str(caught.value)
