"""Gate : un ``Theme(components={…})`` littéral n'a qu'UN lecteur.

Ce qu'elle ferme
----------------
Trois règles de lint — ``theme``, ``variant``, ``shape`` — posent la même
question à l'arbre : « qu'est-ce que ce fichier déclare comme thème ».
Chacune avait sa copie. ``_dict_items`` existait en **deux signatures
différentes** (trois éléments dans deux règles, deux dans la troisième)
et ``variant`` réinscrivait la reconnaissance du nom ``Theme`` à la main.

Ce n'était pas encore un bug : les trois disaient la même chose. C'est le
motif qui PRÉCÈDE un bug, et le dépôt l'a déjà payé une fois —
``theme_vocabulary``, le 2026-08-16 : « deux copies de la même boucle,
donc deux façons de finir par ne plus dire la même chose que le runtime,
et c'est le lint qu'on aurait cru ».

Les deux interdits, et pourquoi DEUX
-------------------------------------
1. **Personne ne redéfinit un lecteur.** Un module de règle qui écrit son
   propre ``dict_items`` ou ``components_arg`` a recommencé la copie.
2. **Personne ne re-reconnaît le nom ``Theme``.** Le premier interdit se
   contourne sans y penser, simplement en appelant sa fonction autrement ;
   celui-ci vise ce qu'elle FAIT — comparer un nom appelé à ``"Theme"`` —
   et c'est ce geste-là qui est le lecteur, quel que soit son nom. C'est
   la leçon de la gate du boilerplate des probes : ancrer sur la forme,
   pas sur le nom d'un helper, « un fichier qui renomme son ``check`` en
   ``verifier`` n'a pas payé la dette, il l'a déguisée ».

Ce qu'elle n'interdit PAS
--------------------------
Qu'une règle lise un thème. C'est leur travail. Elle exige seulement
qu'elles le lisent par ``rules/_theme_calls``, qui ne leur donne aucun
savoir qu'elles n'aient déjà : pas de corpus, pas de plancher, pas de
code de sortie. La pureté posée par le docstring du paquet tient.
"""

from __future__ import annotations

import ast

import pytest

from tests.consistency._discovery import REPO_ROOT

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_sees_both_shapes_of_a_copy``.
MUTATION_PROOF = "test_the_detector_sees_both_shapes_of_a_copy"

#: Le module qui a le DROIT de lire — c'est lui, le lecteur unique.
READER = "_theme_calls"

_RULES_DIR = REPO_ROOT / "bretzel" / "lint" / "rules"

#: 16 règles le 2026-09-11, plus le lecteur. Le plancher attrape un glob
#: cassé : la gate serait verte en n'ayant lu aucun fichier.
_RULES_FLOOR = 12

#: Les noms qu'un lecteur recopié reprendrait presque toujours. Avec ou
#: sans souligné : le souligné ne change rien à la duplication.
_READER_NAMES = frozenset({
    "dict_items", "_dict_items", "components_arg", "_components_arg",
    "component_maps", "_component_maps",
})


def _rule_sources() -> list[tuple[str, str]]:
    """``(nom de module, source)`` pour chaque règle — le lecteur exclu."""
    return [
        (path.stem, path.read_text(encoding="utf-8-sig"))
        for path in sorted(_RULES_DIR.glob("*.py"))
        if path.stem not in {"__init__", READER}
    ]


def redefines_a_reader(source: str) -> set[str]:
    """Les fonctions de lecture que ce module redéfinit pour son compte."""
    return {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name in _READER_NAMES
    }


def recognises_theme_by_hand(source: str) -> bool:
    """Ce module compare-t-il un nom appelé à ``"Theme"`` ?

    On vise le GESTE et pas un nom de fonction : c'est lui, le lecteur.
    Une comparaison à la constante ``"Theme"`` — ``== "Theme"``,
    ``!= "Theme"``, ``in {"Theme"}`` — est la forme que prend toute
    reconnaissance écrite à la main.
    """
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        for side in (node.left, *node.comparators):
            if isinstance(side, ast.Constant) and side.value == "Theme":
                return True
    return False


def test_the_sweep_is_not_vacuous() -> None:
    found = _rule_sources()
    assert len(found) >= _RULES_FLOOR, (
        f"seulement {len(found)} règles découvertes sous {_RULES_DIR} "
        f"(16 le 2026-09-11) — le glob est cassé et la gate ne lit rien."
    )


@pytest.mark.parametrize("name", [n for n, _ in _rule_sources()])
def test_a_rule_does_not_reimplement_the_reader(name: str) -> None:
    source = dict(_rule_sources())[name]

    copies = redefines_a_reader(source)
    assert not copies, (
        f"``{name}`` redéfinit {sorted(copies)} pour son compte.\n"
        f"  Ces lecteurs vivent dans ``bretzel/lint/rules/{READER}.py`` et "
        f"n'y sont qu'une fois, exprès : trois règles posaient la même "
        f"question avec trois copies, dont deux signatures incompatibles "
        f"pour le même nom.\n"
        f"  Importe-les — elles ne donnent à une règle aucun savoir "
        f"qu'elle n'ait déjà."
    )

    if recognises_theme_by_hand(source):
        assert READER in source, (
            f"``{name}`` reconnaît le nom ``Theme`` à la main sans passer "
            f"par ``{READER}``.\n"
            f"  C'est la duplication déguisée : le lecteur n'est pas un "
            f"nom de fonction, c'est ce geste-là. Utilise "
            f"``called_name`` / ``components_arg`` / ``component_maps``."
        )


def test_the_detector_sees_both_shapes_of_a_copy() -> None:
    """Le versant ILLICITE et le versant LICITE, sur du code fabriqué.

    Le versant illicite seul ne dirait rien : un détecteur qui répond
    toujours « oui » ferait rougir toutes les règles et « prouverait »
    qu'il mord.
    """
    copie = (
        "import ast\n"
        "def _dict_items(node):\n"
        "    return []\n"
    )
    assert redefines_a_reader(copie) == {"_dict_items"}, (
        "le détecteur ne voit plus une redéfinition nommée — c'est la "
        "forme exacte d'où l'on vient."
    )

    deguisee = (
        "def lire(call):\n"
        "    if call.func.id != 'Theme':\n"
        "        return None\n"
    )
    assert recognises_theme_by_hand(deguisee), (
        "le détecteur ne voit plus une reconnaissance de ``Theme`` écrite "
        "à la main — renommer sa fonction suffirait alors à contourner la "
        "gate, ce qui est le mode d'échec qu'elle existe pour fermer."
    )

    licite = (
        "from bretzel.lint.rules._theme_calls import dict_items\n"
        "def check(module):\n"
        "    return [k for k, _, _ in dict_items(module.tree)]\n"
    )
    assert not redefines_a_reader(licite), (
        "le détecteur accuse une règle qui IMPORTE le lecteur au lieu de "
        "le recopier — il rougirait sur la bonne façon de faire."
    )
    assert not recognises_theme_by_hand(licite), (
        "le détecteur voit une reconnaissance manuelle là où il n'y a "
        "qu'un import — son taux de faux positifs serait de 100 %."
    )
