"""Règle : un ``TestClient`` construit sans jamais entrer dans le lifespan.

Le silence qu'elle ferme
------------------------

Les routes d'une app Bretzel ne sont pas attachées à l'import : ``@page``
**marque**, ``create_app()`` enregistre — anti-règle 4 — et
``create_app()`` tourne dans le **lifespan**. Or ``TestClient`` ne
déclenche le lifespan que comme gestionnaire de contexte ::

    c = TestClient(app)
    c.get("/")                      # 404, toujours

    with TestClient(app) as c:
        c.get("/")                  # 200

**Pourquoi ça mord si bien** : 404 est exactement ce qu'on obtient avec
une faute de frappe dans le chemin. On va donc relire son ``@page``, son
``include``, son préfixe — et tout est juste. Mesuré le 2026-09-10 :
``examples.kanban`` rend 404 sur ``/`` sans le ``with``, 200 avec, sans
qu'une ligne de l'app bouge.

Le corollaire vaut pour l'introspection : lister les routes avant le
lifespan rend une liste vide, ce qui se lit « mes pages ne se sont pas
enregistrées » au lieu de « je regarde trop tôt ».

Les formes légitimes, mesurées et non supposées
------------------------------------------------

Le corpus de ce dépôt en porte 219 occurrences, et il a servi à cadrer la
règle plutôt qu'à la confirmer :

- ``with TestClient(app) as client:`` — 217 cas. La forme normale.
- ``def _client(): return TestClient(app)`` — 1 cas, et il est CORRECT :
  ses appelants écrivent ``with _client() as client:``. Le ``with`` a
  simplement lieu ailleurs, et une lecture statique d'un seul module ne
  peut pas suivre la valeur jusque-là.
- ``client = TestClient(app)`` puis ``with client:`` plus bas — la forme
  en deux temps, valide elle aussi.

D'où la portée : on ne signale que ce qu'on peut **prouver** inutilisé
dans le module — une construction jetée en instruction nue, ou liée à un
nom qu'aucun ``with`` de ce module ne reprend. Un ``return``, un argument
d'appel, une compréhension : silence. La règle préfère manquer un cas que
d'accuser du code juste, parce qu'un linter qui crie sur la forme
correcte est désactivé à la première session.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "client-de-test-sans-lifespan"

_CLIENT = "TestClient"


def _is_client_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _CLIENT
    return isinstance(func, ast.Attribute) and func.attr == _CLIENT


def _context_exprs(tree: ast.AST) -> tuple[list[ast.expr], set[str]]:
    """Ce qui est ouvert par un ``with`` : les expressions, et les noms.

    Les deux moitiés servent deux formes distinctes — ``with
    TestClient(app)`` d'un côté, ``client = TestClient(app)`` suivi de
    ``with client`` de l'autre.
    """
    exprs: list[ast.expr] = []
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        for item in node.items:
            exprs.append(item.context_expr)
            if isinstance(item.context_expr, ast.Name):
                names.add(item.context_expr.id)
    return exprs, names


def check(module: Module) -> list[Finding]:
    """Les clients de test qui n'entreront jamais dans le lifespan."""
    ouverts, noms_ouverts = _context_exprs(module.tree)
    ouverts_ids = {id(e) for e in ouverts}

    # Chaque suspect porte son SUJET : le nom auquel il est lié, sinon
    # l'appel lui-même. La gate des sondes l'exige, et pour une bonne
    # raison — un message qui ne nomme pas son sujet ne peut être
    # asserté que sur sa prose, et une mutation passe alors inaperçue.
    suspects: list[tuple[ast.Call, str]] = []
    for node in ast.walk(module.tree):
        # Instruction nue : `TestClient(app)` seul sur sa ligne, ou
        # `TestClient(app).get(...)`, qui ne peut plus rien ouvrir.
        if isinstance(node, ast.Expr):
            valeur = node.value
            if _is_client_call(valeur):
                suspects.append((valeur, ast.unparse(valeur)))  # type: ignore[arg-type]
            elif (
                isinstance(valeur, ast.Call)
                and isinstance(valeur.func, ast.Attribute)
                and _is_client_call(valeur.func.value)
            ):
                interne = valeur.func.value
                suspects.append((interne, ast.unparse(interne)))  # type: ignore[arg-type]
        # Liaison à un nom qu'aucun `with` de ce module ne reprend.
        elif isinstance(node, ast.Assign) and _is_client_call(node.value):
            cibles = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if cibles and not any(nom in noms_ouverts for nom in cibles):
                suspects.append((node.value, cibles[0]))  # type: ignore[arg-type]

    return [
        Finding(
            rule=RULE,
            path=module.path,
            line=call.lineno,
            message=(
                f"`{sujet}` n'entre jamais dans le lifespan — toutes les "
                f"pages rendront 404."
            ),
            hint=(
                "Les routes s'enregistrent dans `create_app()`, que le "
                "lifespan déclenche ; `TestClient` ne l'ouvre qu'en "
                "gestionnaire de contexte. Écris `with TestClient(app) as "
                "client:`. Le 404 qui en découle ressemble à une faute de "
                "chemin, d'où la règle."
            ),
        )
        for call, sujet in suspects
        if id(call) not in ouverts_ids
    ]
