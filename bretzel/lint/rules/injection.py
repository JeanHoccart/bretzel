"""Règle : ``ui.html`` avec autre chose qu'un littéral.

``ui.html`` injecte du balisage **verbatim, jamais échappé**. Son nœud le
dit depuis toujours (``core/tree.py`` : *« every occurrence is a candidate
XSS sink and should be auditable »*), et le composant s'appelle
délibérément ``ui.html`` et non ``ui.raw_html`` — un nom effrayant
n'avertit qu'une personne, une fois, au moment où elle l'écrit.

Ce qui avertit à chaque fois, c'est un outil. Dans le dépôt du framework
c'est une liste gelée d'appels (``test_ui_html_call_sites_are_listed``) ;
pour une app, geler n'a aucun sens — mais **juger la littéralité** en a.

- ``ui.html("<hr>")`` → littéral, aucun chemin depuis une entrée
  utilisateur : ignoré.
- ``ui.html(article.body)`` → la valeur vient d'ailleurs. Signalé, parce
  que c'est exactement la forme qui transforme un champ de base de données
  en script exécuté.

La règle ne prétend pas détecter une XSS : elle rend le choix **visible**,
pour qu'il soit posé plutôt que subi. Le constructeur, lui, refuse déjà
une `ClientBinding` — faire écrire du balisage au runtime depuis l'état
client serait un puits piloté par le client.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "html-non-litteral"


def _is_literal(node: ast.expr) -> bool:
    """Un littéral, ou une concaténation/f-string de littéraux seuls."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return all(isinstance(part, ast.Constant) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_literal(node.left) and _is_literal(node.right)
    return False


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "html"
            and isinstance(func.value, ast.Name)
            and func.value.id == "ui"
        ):
            continue
        argument = node.args[0] if node.args else None
        if argument is None:
            argument = next((kw.value for kw in node.keywords if kw.arg == "text"), None)
        if argument is None or _is_literal(argument):
            continue
        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=node.lineno,
                message=(
                    "`ui.html(…)` reçoit une valeur non littérale : le balisage "
                    "est injecté verbatim, jamais échappé."
                ),
                hint=(
                    "Assainis (bleach/nh3) avant, ou passe par `ui.markdown` "
                    "qui échappe le HTML embarqué et réécrit les URLs "
                    "dangereuses. Si la valeur est sûre, dis-le en commentaire "
                    "au call-site."
                ),
            )
        )
    return findings
