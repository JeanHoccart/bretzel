"""La lecture d'un ``Theme(components={…})`` littéral — une seule fois.

Ce n'est **pas** un module d'helpers AST, et la nuance décide de ce qui a
le droit d'entrer ici : trois règles — ``theme``, ``variant``, ``shape``
— posent la même question à l'arbre, « qu'est-ce que ce fichier déclare
comme thème », et c'est cette question-là qui est partagée. Les autres
règles ne l'ont pas. Un fourre-tout d'helpers attirerait exactement le
couplage que la pureté des règles protège.

Pourquoi l'extraction
---------------------
Les trois lisaient la même chose avec leur propre copie. ``_dict_items``
existait en **deux signatures différentes** — trois éléments dans
``theme`` et ``shape``, deux dans ``variant`` — et ``variant``
réinscrivait la reconnaissance du nom ``Theme`` à la main. Ce n'était pas
encore un bug : les trois disaient la même chose. C'était le motif qui
précède un bug, le même que ``theme_vocabulary`` a fermé le 2026-08-16 —
deux copies d'une boucle finissent par ne plus dire la même chose que le
runtime, et c'est le lint qu'on aurait cru.

Ce que ça NE donne pas aux règles
----------------------------------
Rien qu'elles n'aient déjà. Pas de corpus, pas de plancher, pas de code
de sortie : uniquement de la lecture d'arbre, sur l'arbre qu'on lui
passe. La pureté posée par le docstring du paquet tient.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

#: Le nom sous lequel un thème se construit. Reconnu en tant que NOM,
#: appelé directement (``Theme(...)``) ou par attribut
#: (``bretzel.Theme(...)``) : une règle statique ne résout pas les
#: imports, et exiger une forme unique refuserait du code correct.
THEME_CALLABLE = "Theme"


def called_name(call: ast.Call) -> str | None:
    """Le nom appelé, qu'il soit nu ou attribut — ``None`` sinon."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def dict_items(node: ast.expr) -> list[tuple[str, ast.expr, ast.expr]]:
    """Les entrées ``"littéral": valeur`` d'un dict littéral.

    Rend ``(clé, nœud de la clé, nœud de la valeur)`` : le nœud de la clé
    porte le numéro de ligne, dont une règle a besoin pour situer son
    constat. Un appelant qui n'en veut pas ignore l'élément du milieu —
    c'est moins cher que deux signatures, qui est l'état d'où l'on vient.

    Tout le reste — un ``**spread``, une clé calculée, une variable à la
    place du dict — est ignoré sans bruit : la règle est statique, et
    signaler ce qu'elle ne peut pas lire produirait du bruit sur du code
    correct.
    """
    if not isinstance(node, ast.Dict):
        return []
    return [
        (key.value, key, value)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


def components_arg(call: ast.Call) -> ast.expr | None:
    """Le ``components=`` d'un appel qui ressemble à ``Theme(...)``.

    ``None`` si ce n'est pas un ``Theme``, ou s'il n'a pas ce
    mot-clé — un thème peut ne surcharger que sa palette.
    """
    if called_name(call) != THEME_CALLABLE:
        return None
    for keyword in call.keywords:
        if keyword.arg == "components":
            return keyword.value
    return None


def component_maps(tree: ast.Module) -> Iterator[ast.expr]:
    """Chaque ``components={…}`` des ``Theme(...)`` de cet arbre.

    Un module peut en porter plusieurs — un thème par écran, un thème de
    test à côté du vrai. Les rendre tous plutôt que le premier est ce qui
    évite qu'une règle juge sur la moitié d'un fichier.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            components = components_arg(node)
            if components is not None:
                yield components
