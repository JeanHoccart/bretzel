"""Règle : un lien DANS un lien — le parseur défait la carte.

Le silence qu'elle ferme
------------------------

Le HTML sérialisé est juste. C'est le NAVIGATEUR qui le réécrit ::

    with ui.card(href=f"/classe/{cible}"):     # rend un <a>
        ui.text(code)
        ui.link(label="cahier", href=...)      # un <a> dans un <a>

HTML interdit l'ancre imbriquée. Le parseur ferme donc le premier ``<a>``
au moment où il rencontre le second, et **tout ce qui suit atterrit
dehors** — hors de la carte, dans le flux du parent.

Mesuré sur ``examples/ecole`` le 2026-09-12 : la carte rendait 130 px de
vide et le nom de la salle s'affichait dans la case de l'heure suivante.
Aucune erreur JS, aucune requête en échec, et ``TestClient`` rendait
exactement le bon document — la faute n'existe qu'après le parseur. À
l'écran, ça ne ressemble pas à un défaut de structure : ça ressemble à un
problème d'espacement, ce qui envoie chercher au mauvais endroit.

Ce que la règle lit
--------------------

Un conteneur qui devient une ancre — ``href=`` sur un composant qui rend
un ``<a>`` — et, dans son corps ``with``, un appel qui rend une ancre à
son tour. Les deux familles sont **découvertes** par le même critère :
un composant dont l'appel porte un ``href=``. Pas de table écrite ici.

Le balayage ne redescend pas dans un ``with`` imbriqué qui rouvre une
ancre : le premier niveau suffit, et le cas ne s'est jamais présenté.

⚠️ Ce que la règle ne dit PAS
------------------------------

Qu'un ``href=`` calculé soit sans danger. ``ui.card(href=x)`` compte,
quelle que soit la provenance de ``x`` : c'est la PRÉSENCE du paramètre
qui fait l'ancre, pas sa valeur. Un ``href=None`` littéral, lui, ne la
fait pas — et il est lu comme tel.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: Le nom de la règle, tel qu'il s'affiche dans un constat.
RULE = "lien-dans-un-lien"


def _call_name(node: ast.expr) -> str | None:
    """``card`` pour ``ui.card(...)``, ``link`` pour ``ui.link(...)``."""
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _makes_an_anchor(call: ast.Call) -> bool:
    """L'appel porte-t-il un ``href=`` qui ne soit pas littéralement nul ?

    ``href=None`` est écrit exprès dans ce dépôt pour dire « pas de lien
    ici » (une tuile qui n'a pas encore sa route). Le lire comme une ancre
    produirait un constat sur du code qui dit précisément le contraire.
    """
    for kw in call.keywords:
        if kw.arg != "href":
            continue
        return not (
            isinstance(kw.value, ast.Constant) and kw.value.value is None
        )
    return False


def _anchors_inside(body: list[ast.stmt]) -> list[ast.Call]:
    return [
        node
        for stmt in body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Call) and _makes_an_anchor(node)
    ]


def check(module: Module) -> list[Finding]:
    """Les ancres ouvertes dans le corps d'une autre ancre."""
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        dehors = [
            item.context_expr
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
            and _makes_an_anchor(item.context_expr)
        ]
        if not dehors:
            continue
        porteur = dehors[0]
        for dedans in _anchors_inside(node.body):
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=dedans.lineno,
                    message=(
                        f"`{_call_name(dedans)}` porte un `href=` à "
                        f"l'intérieur de `{_call_name(porteur)}`, qui en "
                        f"porte un aussi — un `<a>` dans un `<a>`."
                    ),
                    hint=(
                        "HTML l'interdit : le parseur du navigateur FERME "
                        "l'ancre extérieure en rencontrant l'intérieure, et "
                        "tout ce qui suit sort du conteneur. Le HTML "
                        "sérialisé reste juste, donc aucun test de rendu ne "
                        "le voit. Retire le `href=` du conteneur et pose "
                        "DEUX liens explicites à l'intérieur."
                    ),
                )
            )
    return findings
