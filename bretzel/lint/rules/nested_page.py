"""Règle : une ``@page`` déclarée dans un corps de fonction, que rien ne récolte.

Le silence qu'elle ferme
------------------------

``@page`` **marque** la fonction, elle n'enregistre rien — c'est
l'anti-règle 4, et c'est ce qui rend l'ordre des imports sans effet.
L'enregistrement vient d'``include``, qui balaie les callables de
**premier niveau** d'un module. Une fonction définie dans le corps d'une
autre n'est attribut d'aucun module : le balayage ne peut pas la voir.

::

    def monter_app():
        app = Bretzel(...)

        @page("/")                 # marquée, jamais récoltée
        def accueil() -> None:
            ui.text("salut")

        app.include(__name__)      # ne voit que le premier niveau
        return app

L'app démarre, ne dit rien, et rend **404 sur toutes ses pages**. Or 404
est exactement ce que rend une faute de frappe dans le chemin : on relit
son ``@page``, son préfixe, son ``include`` — et tout est juste.

Un cas réel, dans ce dépôt
---------------------------

``tests/unit/server/test_protocol_compat_gate.py`` déclare ainsi une page
``/`` depuis le 2026-08-01. Mesuré le 2026-09-10 : ``GET /`` rend **404**
et ``home`` n'est pas un attribut du module. Les tests passent parce
qu'ils POSTent vers la route d'action et ne visitent jamais la page —
donc rien ne l'a jamais signalé.

Les trois formes LÉGITIMES, et pourquoi la règle les épargne
-------------------------------------------------------------

``include`` accepte trois choses, et deux d'entre elles rendent une page
imbriquée parfaitement valide :

1. ``app.include(accueil)`` — un callable marqué, passé directement ;
2. ``PAGES.append(accueil)`` / ``return accueil`` — l'itérable, que sa
   docstring décrit comme le chemin des « pages générées dynamiquement
   qu'on ne peut pas lier à un nom de module » ;
3. le module, qui est le seul cas où l'imbrication tue la page.

La règle ne peut pas savoir ce que fait ``include``, mais elle sait lire
une chose : **le nom de la fonction est-il référencé après sa
définition ?** Dans les formes 1 et 2 il l'est forcément — c'est ainsi
qu'on la remet à quelqu'un. Dans la forme 3, il ne l'est jamais. Le
critère n'est donc pas « imbriquée », c'est « imbriquée ET jamais
reprise » : une page qu'aucune expression ne nomme ne peut être récoltée
par personne.

Mesuré sur ``tests/`` (75 déclarations imbriquées), c'est ce qui sépare
le cas réel ci-dessus de la grande majorité, qui passe la fonction à
``include``.

``error_page`` est jugée de la même façon : ``include`` la balaie par le
même chemin, et une page d'erreur muette est encore plus discrète — on ne
la visite qu'en panne.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "page-declaree-dans-une-fonction"

#: Les marques qu'``include`` récolte au premier niveau d'un module.
_MARKS = frozenset({"page", "error_page"})

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _decorator_name(node: ast.expr) -> str | None:
    """``page`` pour ``@page``, ``@page("/")``, ``@bretzel.page("/")``."""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_marked(func: _Func) -> bool:
    return any(_decorator_name(d) in _MARKS for d in func.decorator_list)


def _nested_functions(tree: ast.AST) -> list[tuple[_Func, _Func]]:
    """Les couples ``(fonction imbriquée, fonction qui la contient)``.

    Une fonction imbriquée dans une CLASSE n'en fait pas partie : une
    méthode est un attribut de sa classe, pas une locale, et le cas ne
    se présente pas pour une page. On ne descend donc que dans les corps
    de fonction.
    """
    couples: list[tuple[_Func, _Func]] = []

    def descendre(node: ast.AST, enclosing: _Func | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                if enclosing is not None:
                    couples.append((child, enclosing))
                descendre(child, child)
            elif isinstance(child, ast.ClassDef):
                descendre(child, None)
            else:
                descendre(child, enclosing)

    descendre(tree, None)
    return couples


def _is_referenced(name: str, scope: _Func) -> bool:
    """Le nom est-il lu quelque part dans la fonction qui le contient ?

    Un ``ast.Name`` en LOAD suffit : ``include(accueil)``,
    ``PAGES.append(accueil)``, ``return accueil`` en produisent tous un.
    La définition, elle, n'est pas un ``Name`` — elle ne peut donc pas
    se compter elle-même.
    """
    return any(
        isinstance(node, ast.Name)
        and node.id == name
        and isinstance(node.ctx, ast.Load)
        for node in ast.walk(scope)
    )


def check(module: Module) -> list[Finding]:
    """Les pages marquées qu'aucun balayage ne peut atteindre."""
    findings: list[Finding] = []
    for func, enclosing in _nested_functions(module.tree):
        if not _is_marked(func) or _is_referenced(func.name, enclosing):
            continue
        mark = next(
            n for d in func.decorator_list if (n := _decorator_name(d)) in _MARKS
        )
        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=func.lineno,
                message=(
                    f"`@{mark}` sur `{func.name}`, déclarée dans "
                    f"`{enclosing.name}()` et jamais reprise — aucun "
                    f"`include` ne peut la récolter."
                ),
                hint=(
                    "`@page` MARQUE la fonction ; c'est `include` qui "
                    "enregistre, en balayant le premier niveau d'un module. "
                    "Une locale n'y est pas, et l'app rend 404 sans rien "
                    "dire. Remonte-la au niveau du module, ou passe-la "
                    "directement : `app.include(" + func.name + ")`."
                ),
            )
        )
    return findings
