"""Gate : la règle `classe-doublee-par-une-prop` lit le composant VIVANT.

`bretzel.lint.rules.specificity` ne porte aucune table `justify →
justify-*` : elle la dérive de `THEME_TABLES`, du `THEME` et des défauts
de `__reactive_props__`. C'est ce qui la garde juste quand un thème
change — et c'est exactement ce qui peut la rendre **muette** sans qu'elle
rougisse.

⚠️ Le mode d'échec que ce fichier ferme est celui de `gates.md` §
« une gate qui cherche un NOM peut être vide sans le dire » : `THEME_TABLES`
est un identifiant codé en dur dans la règle. Renommé, déplacé, retiré de
`Flex`, il ne lève pas — `getattr(cls, "THEME_TABLES", None)` rend `None`,
`_judged()` rend un dict vide, et la règle devient une fonction qui ne
signale plus jamais rien. Un `pytest` vert, un `bretzel check` vert, et le
bug de départ qui repasse.

D'où la forme, écrite à l'envers d'une interdiction : on ne compte pas les
contrevenants, on compte **ce que la règle croit surveiller**, et on exige
que le rendu réel le confirme.
"""

from __future__ import annotations

import re

import pytest

from bretzel.lint.rules.specificity import _Family, _family_members, _judged
from tests.consistency._discovery import rendered_html_of

#: Les props de la famille flex qui posent une classe. `wrap` (groupe
#: scalaire) et `grow` (classes à variant `*:`, et défaut vide) n'en sont
#: pas — la règle les écarte, et ce plancher dit qu'elle a raison de ne
#: garder QUE ces quatre.
_EXPECTED_PROPS = frozenset({"align", "direction", "gap", "justify"})

#: Le plancher de population. Cinq composants déclarent `THEME_TABLES`
#: (mesuré le 2026-09-06) ; borner, pas figer — un sixième est le bienvenu.
_FLOOR = frozenset({"flex", "hstack", "pane", "vstack", "viewport"})


def _class_attr(html: str) -> str:
    match = re.search(r'class="([^"]*)"', html)
    return match.group(1) if match else ""


def test_the_rule_sees_the_flex_family() -> None:
    """Plancher : `_judged()` n'est pas vide, et il couvre ce qu'on croit.

    Sans lui, retirer `THEME_TABLES` de `Flex` rendrait la règle
    silencieuse et TOUT le reste vert — y compris la sonde de
    `test_lint_rules_are_not_vacuous`, qui ne mesure que ce qui tombe.
    """
    judged = _judged()
    assert set(judged) >= _FLOOR, (
        f"la règle ne juge plus {sorted(_FLOOR - set(judged))}. Si "
        f"`THEME_TABLES` a été renommé ou déplacé, `_judged()` se vide en "
        f"silence et la règle cesse de signaler quoi que ce soit."
    )


@pytest.mark.parametrize("ui_name", sorted(_FLOOR))
def test_every_prop_that_poses_a_class_is_watched(ui_name: str) -> None:
    """Les quatre props qui posent une classe sont toutes surveillées."""
    watched = {family.prop for family in _judged()[ui_name]}
    assert watched == _EXPECTED_PROPS, (
        f"`ui.{ui_name}` : props surveillées {sorted(watched)}, attendu "
        f"{sorted(_EXPECTED_PROPS)}. Une prop qui sort du jeu emporte avec "
        f"elle toute une famille de classes, sans un seul constat en moins "
        f"ailleurs."
    )


@pytest.mark.parametrize("ui_name", sorted(_FLOOR))
def test_the_derived_family_is_not_a_singleton(ui_name: str) -> None:
    """Une famille réduite à une classe est une dérivation qui a raté.

    Le cas concret : le préfixe se déduit des classes émises, et si la
    déduction échoue la famille est **vide** — ce qui se lit comme « rien à
    signaler ». Deux membres au moins, sinon la règle ne peut plus opposer
    une classe à une autre.
    """
    for family in _judged()[ui_name]:
        assert len(family.members) >= 2, (
            f"`ui.{ui_name}` : la famille de `{family.prop}=` n'a que "
            f"{sorted(family.members)}. Le préfixe n'a pas pu être déduit "
            f"du thème."
        )


@pytest.mark.parametrize("ui_name", sorted(_FLOOR))
def test_what_the_rule_says_is_posed_is_really_rendered(ui_name: str) -> None:
    """Le versant qui compte : le rendu réel confirme la dérivation.

    C'est la seule assertion **indépendante** du fichier — les autres
    relisent la même source que la règle. Ici on construit le composant et
    on lit son attribut ``class`` : si la règle annonce que `justify=`
    pose `justify-start` par défaut, le HTML doit le porter.

    Ce qu'elle attrape et qu'aucune lecture de table ne verrait : une prop
    dont le rendu cesse de consulter son groupe (le kwarg mort, mode
    d'échec dominant du dépôt), un défaut changé d'un côté seulement, un
    groupe renommé dans un `THEME` mais pas dans `THEME_TABLES`.
    """
    from bretzel.components import ui

    html = rendered_html_of(getattr(ui, ui_name))
    assert html is not None, f"`ui.{ui_name}` n'a pas pu être rendu"
    rendered = _class_attr(html).split()

    for family in _judged()[ui_name]:
        posed = family.emits.get(family.default, "")
        assert posed, (
            f"`ui.{ui_name}` : `{family.prop}=` a pour défaut "
            f"{family.default!r}, que le groupe de thème ne rend pas."
        )
        missing = [token for token in posed.split() if token not in rendered]
        assert not missing, (
            f"`ui.{ui_name}()` : la règle annonce que `{family.prop}=` pose "
            f"{posed!r} (son défaut {family.default!r}), mais le HTML rendu "
            f"ne porte pas {missing}.\n  class rendu : {' '.join(rendered)}\n"
            f"  La règle raisonnerait sur une classe qui n'existe plus."
        )


def test_a_value_the_theme_spells_otherwise_stays_in_the_family() -> None:
    """`justify-center` est de la famille, alors que le thème rend autre chose.

    Le thème flex rend `center` en `[justify-content:safe_center]` — un
    centrage `safe`, pour qu'un contenu trop haut ne rende pas son haut
    inatteignable. L'utilitaire nommé `justify-center`, lui, reste ce que
    tout le monde écrit dans `classes=`, et c'est LUI qui a produit le bug
    d'origine.

    La règle le rattrape en recollant le préfixe aux **clés** de la table.
    Un retour à « la famille = les classes émises » le perdrait sans que
    rien d'autre ne bouge — et c'est le cas exact qu'on veut attraper.
    """
    justify = _family(_judged()["vstack"], "justify")
    assert "justify-center" in justify.members, (
        "`justify-center` n'est plus dans la famille de `justify=`. Le "
        "thème le rend en forme `[justify-content:…]`, donc seule la "
        "recollure préfixe + clé le fait entrer — sans elle, le bug qui a "
        "motivé la règle repasse."
    )
    assert justify.members["justify-center"] == "center"


def test_a_neighbour_prefix_does_not_swallow_the_family() -> None:
    """`flex-1` n'est pas une direction, et c'est ce qui rend la règle tenable.

    La famille de `direction=` partage son préfixe avec quatre utilitaires
    Tailwind courants (`flex-1`, `flex-auto`, `flex-none`, `flex-nowrap`).
    Une famille définie par le préfixe seul ferait un faux positif par
    usage — c'est le versant LICITE de la mutation, celui qui trouve ce
    qu'on ne cherchait pas (`gates.md`).
    """
    direction = _family(_judged()["flex"], "direction")
    intruders = [
        token
        for token in ("flex-1", "flex-auto", "flex-none", "flex-nowrap", "flex-wrap")
        if token in direction.members
    ]
    assert not intruders, (
        f"{intruders} sont entrés dans la famille de `direction=`. Aucun "
        f"n'est une direction : la règle signalerait du code correct, et "
        f"c'est ainsi qu'un outil se fait désactiver."
    )


def test_the_derivation_catches_a_fabricated_table_and_spares_a_mixed_one() -> None:
    """Preuve que la dérivation mord, sur des tables qu'elle n'a jamais vues.

    Versant qui MORD — une table dont une valeur est rendue en forme
    arbitraire : les trois classes nommées doivent sortir, la clé recollée
    au préfixe comprise. C'est le mécanisme exact du `center` du thème
    flex, joué sur un préfixe qui n'existe nulle part dans le dépôt, donc
    sans pouvoir s'appuyer sur ce qui est déjà là.

    Versant qui ÉPARGNE — une table à deux préfixes n'a pas de famille :
    la dérivation doit rendre **rien** plutôt que d'inventer un voisinage.
    C'est le versant qui coûte, et celui qui trouve les faux positifs.
    """
    fabricated = _family_members(
        {
            "start": "place-start",
            "center": "[place-content:safe_center]",
            "end": "place-end",
        }
    )
    assert fabricated == {
        "place-start": "start",
        "place-center": "center",
        "place-end": "end",
    }, (
        "la dérivation ne reconstruit plus la classe nommée d'une valeur "
        "que le thème rend en forme arbitraire — c'est par là que "
        "`justify-center` entre dans la famille."
    )

    assert _family_members({"a": "left-0", "b": "top-0"}) == {}, (
        "une table à deux préfixes n'a pas de famille : en fabriquer une "
        "reviendrait à opposer `left-*` et `top-*`, qui ne se disputent "
        "rien."
    )


def _family(families: tuple[_Family, ...], prop: str) -> _Family:
    found = next((f for f in families if f.prop == prop), None)
    assert found is not None, f"aucune famille pour `{prop}=`"
    return found
