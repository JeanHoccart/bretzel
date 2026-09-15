"""Règle : une surcharge de thème qui garde le NOM et change la FORME.

Le silence qu'elle ferme
------------------------

``theme-vocabulaire-inconnu`` refuse les noms que rien ne lit, mais il
**exempte volontairement** les groupes adressés par une valeur
(``sizes``, ``variants``, ``paddings``…) : y ajouter une clé est la façon
supportée de déclarer sa propre variante, et la signaler condamnerait le
seul moyen propre de dévier du thème livré.

Cette règle passe par ce trou sans rouvrir la porte. Elle ne juge que les
clés qui **existent déjà** dans le thème livré, et une seule chose : leur
forme. Une clé neuve reste exempte — elle n'a pas de contrepartie livrée,
donc il n'y a rien à contredire.

Les deux sens, mesurés le 2026-09-10
-------------------------------------

Ils ne se comportent pas pareil, et c'est ce qui rend le premier
prioritaire ::

    # `button.sizes.md` est livré en CHAÎNE — on écrit un dict
    Theme(components={"button": {"sizes": {"md": {"root": "h-8 px-3"}}}})

Le bouton perd **tous** ses jetons de taille. Mesuré sur son ``class=`` :
``h-10 px-4 text-sm gap-2`` avant, plus rien après. La page rend en 200,
le HTML est valide, aucun test ne rougit — le bouton est juste nu, à la
taille de son contenu. C'est la famille que ``check`` existe pour
attraper.

::

    # `select.sizes.md` est livré en DICT — on écrit une chaîne
    Theme(components={"select": {"sizes": {"md": "h-8 px-3"}}})

Celui-là lève : ``AttributeError: 'str' object has no attribute 'get'``.
Bruyant, donc moins urgent — mais la levée arrive au **rendu**, donc sur
une page peu exercée elle attend la production, et elle ne nomme ni le
thème, ni le composant, ni la clé. Un constat statique vaut mieux qu'une
trace de pile.

Ce qu'elle ne lit pas, et se tait
----------------------------------

Une valeur qu'une lecture statique ne peut pas classer — une variable, un
appel, un ``**spread``, une clé calculée — est ignorée sans bruit. Même
refus que dans :mod:`bretzel.lint.rules.theme` : signaler ce qu'on ne
peut pas lire produit du bruit sur du code correct.

Un groupe **scalaire** n'a pas d'entrées, donc pas de forme à comparer :
:func:`~bretzel.introspect.theme_shapes` ne le décrit pas, et la règle
n'a rien à en dire.

La forme livrée vient de :func:`~bretzel.introspect.theme_shapes` —
jamais d'une table écrite ici. Une table de noms dans un linter dérive du
code qu'elle prétend juger ; c'est le même refus que ``variant`` et
``sizes`` opposent, et la raison pour laquelle ``theme_vocabulary`` a été
centralisée le 2026-08-16.

⚠️ Dette notée, pas payée : c'est la **troisième** règle à lire un
``Theme(components={…})`` littéral (avec ``theme`` et ``variant``), et
chacune porte sa version des deux mêmes helpers d'AST. La convention du
paquet est « une règle est pure, elle ne connaît ni corpus ni plancher »,
donc on l'a suivie plutôt que de refactorer deux règles qui marchent ;
l'extraction est inscrite dans ``.claude/work/todo.md``.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "palier-de-theme-change-de-forme"

#: Ce que rend une valeur qu'on sait classer. ``None`` = illisible.
_DICT = "dict"
_STR = "str"


def _written_shape(node: ast.expr) -> str | None:
    """La forme d'une valeur ÉCRITE, ou ``None`` si elle est illisible.

    ``ast.JoinedStr`` (une f-string) et la concaténation comptent comme
    des chaînes : elles produisent une chaîne à coup sûr, quel que soit
    leur contenu. C'est la forme qu'on juge, pas la valeur — donc il n'y
    a pas besoin de savoir ce que l'interpolation vaudra.
    """
    if isinstance(node, ast.Dict):
        return _DICT
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _STR
    if isinstance(node, ast.JoinedStr):
        return _STR
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _written_shape(node.left)
        return left if left == _STR and _written_shape(node.right) == _STR else None
    return None


def _consequence(shipped: str, written: str) -> tuple[str, str]:
    """Ce que la faute produit vraiment — message court, indice long."""
    if shipped == _STR and written == _DICT:
        return (
            "le palier perd TOUS ses jetons",
            "Le thème livre une chaîne de classes ici. Un dict la remplace, "
            "et le composant ne compose plus rien : il rend à sa taille de "
            "contenu, en 200, sans erreur. Écris la chaîne entière.",
        )
    return (
        "le rendu LÈVE",
        "Le thème livre une table de sous-slots ici. Une chaîne la remplace, "
        "et le composant lève `AttributeError: 'str' object has no attribute "
        "'get'` au rendu. Surcharge les sous-slots que tu changes — la fusion "
        "est profonde, les autres restent au thème livré.",
    )


def check(module: Module) -> list[Finding]:
    """Les surcharges de thème dont la forme contredit le thème livré."""
    calls = list(component_maps(module.tree))
    if not calls:
        return []

    from bretzel.introspect import theme_shapes

    shapes = theme_shapes()
    findings: list[Finding] = []
    for components in calls:
        for comp_name, _, comp_value in dict_items(components):
            groups = shapes.get(comp_name)
            if groups is None:
                # `theme-vocabulaire-inconnu` le dit déjà, et mieux.
                continue
            for group, _, group_value in dict_items(comp_value):
                entries = groups.get(group)
                if entries is None:
                    continue
                for key, key_node, value_node in dict_items(group_value):
                    shipped = entries.get(key)
                    if shipped is None:
                        # Clé NEUVE — c'est une extension, pas une faute.
                        continue
                    written = _written_shape(value_node)
                    if written is None or written == shipped:
                        continue
                    court, indice = _consequence(shipped, written)
                    findings.append(
                        Finding(
                            rule=RULE,
                            path=module.path,
                            line=key_node.lineno,
                            message=(
                                f"`{comp_name}.{group}.{key}` est livré en "
                                f"`{shipped}` et surchargé en `{written}` — "
                                f"{court}."
                            ),
                            hint=(
                                f"{indice} "
                                f"`bretzel describe {comp_name}` nomme ses groupes."
                            ),
                        )
                    )
    return findings
