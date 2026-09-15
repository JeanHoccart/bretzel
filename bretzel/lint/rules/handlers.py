"""Règle : un handler ne peut pas être un lambda.

Le framework adresse un handler par son ``module::qualname`` et le
re-résout via ``sys.modules`` à l'arrivée de l'action — c'est ce qui
permet au client de ne transporter qu'un identifiant signé plutôt qu'une
référence. Un lambda n'a pas de nom adressable, donc
``encode_handler_id`` **lève** (``HandlerError: Lambda handlers are
forbidden``). Vérifié le 2026-08-16 : lambda et closure refusés,
fonction top-level acceptée.

C'est donc un échec **certain**, pas une heuristique — et il se voit
statiquement, avant même de lancer l'app. La forme est naturelle à écrire
(``on_click=lambda: state.count + 1``) et c'est précisément pour ça
qu'elle vaut une règle : rien dans la syntaxe ne suggère qu'elle est
interdite.

⚠️ **Les closures ne sont PAS couvertes ici**, alors qu'elles sont
refusées de la même façon (``Closure handler 'make.<locals>.inner'``). Les
détecter demande de résoudre un nom jusqu'à sa définition et de savoir si
elle est imbriquée — une analyse de portée que ce module ne fait pas.
L'omission est déclarée plutôt que silencieuse : le lambda est le cas
fréquent, la closure reste rattrapée à l'exécution avec un message clair.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "handler-lambda"


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if not keyword.arg or not keyword.arg.startswith("on_"):
                continue
            if not isinstance(keyword.value, ast.Lambda):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=keyword.value.lineno,
                    message=(
                        f"`{keyword.arg}=lambda …` : le framework adresse un "
                        f"handler par son `module::qualname` et le re-résout "
                        f"via `sys.modules`. Un lambda n'a pas de nom "
                        f"adressable — ça lève au rendu."
                    ),
                    hint=(
                        "Écris une fonction au top-level du module et passe-la "
                        "par son nom. Pour figer un argument, "
                        "`functools.partial(handler, item_id)`."
                    ),
                )
            )
    return findings
