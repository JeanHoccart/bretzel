"""Rule: a ``TestClient`` built without ever entering the lifespan.

The silence it closes
---------------------

A Bretzel app's routes are not attached at import: ``@page`` **marks**,
``create_app()`` registers — anti-rule 4 — and ``create_app()`` runs in
the **lifespan**. And ``TestClient`` only triggers the lifespan as a
context manager ::

    c = TestClient(app)
    c.get("/")                      # 404, always

    with TestClient(app) as c:
        c.get("/")                  # 200

**Why it bites so well**: 404 is exactly what one gets from a typo in the
path. So one re-reads one's ``@page``, one's ``include``, one's prefix —
and everything is correct. Measured on 2026-09-10: ``examples.kanban``
returns 404 on ``/`` without the ``with``, 200 with it, without a line of
the app moving.

The corollary holds for introspection: listing the routes before the
lifespan returns an empty list, which reads as "my pages did not
register" instead of "I am looking too early".

The legitimate forms, measured and not assumed
----------------------------------------------

This repository's corpus carries 219 occurrences, and it served to frame
the rule rather than to confirm it:

- ``with TestClient(app) as client:`` — 217 cases. The normal form.
- ``def _client(): return TestClient(app)`` — 1 case, and it is CORRECT:
  its callers write ``with _client() as client:``. The ``with`` simply
  happens elsewhere, and a static read of one module cannot follow the
  value that far.
- ``client = TestClient(app)`` then ``with client:`` further down — the
  two-step form, valid as well.

Hence the scope: we only report what can be **proven** unused within the
module — a construction thrown away as a bare statement, or bound to a
name no ``with`` in this module takes up. A ``return``, a call argument, a
comprehension: silence. The rule would rather miss a case than accuse
correct code, because a linter that shouts at the correct form is
disabled in the first session.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "test-client-without-lifespan"

_CLIENT = "TestClient"


def _is_client_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _CLIENT
    return isinstance(func, ast.Attribute) and func.attr == _CLIENT


def _context_exprs(tree: ast.AST) -> tuple[list[ast.expr], set[str]]:
    """What a ``with`` opens: the expressions, and the names.

    The two halves serve two distinct forms — ``with TestClient(app)`` on
    one side, ``client = TestClient(app)`` followed by ``with client`` on
    the other.
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
    """The test clients that will never enter the lifespan."""
    opened, opened_names = _context_exprs(module.tree)
    opened_ids = {id(e) for e in opened}

    # Each suspect carries its SUBJECT: the name it is bound to,
    # otherwise the call itself. The probes' gate requires it, and for a
    # good reason — a message that does not name its subject can only be
    # asserted on its prose, and a mutation then goes unnoticed.
    suspects: list[tuple[ast.Call, str]] = []
    for node in ast.walk(module.tree):
        # A bare statement: `TestClient(app)` alone on its line, or
        # `TestClient(app).get(...)`, which can no longer open anything.
        if isinstance(node, ast.Expr):
            value = node.value
            if _is_client_call(value):
                suspects.append((value, ast.unparse(value)))  # type: ignore[arg-type]
            elif (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and _is_client_call(value.func.value)
            ):
                inner = value.func.value
                suspects.append((inner, ast.unparse(inner)))  # type: ignore[arg-type]
        # Bound to a name no `with` in this module takes up.
        elif isinstance(node, ast.Assign) and _is_client_call(node.value):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if targets and not any(name in opened_names for name in targets):
                suspects.append((node.value, targets[0]))  # type: ignore[arg-type]

    return [
        Finding(
            rule=RULE,
            path=module.path,
            line=call.lineno,
            message=(
                f"`{subject}` never enters the lifespan — every page will "
                f"return 404."
            ),
            hint=(
                "The routes register in `create_app()`, which the "
                "lifespan triggers; `TestClient` only opens it as a context "
                "manager. Write `with TestClient(app) as client:`. The "
                "resulting 404 looks like a path typo, hence the rule."
            ),
        )
        for call, subject in suspects
        if id(call) not in opened_ids
    ]
