"""Rule: a link INSIDE a link — the parser undoes the card.

The silence it closes
---------------------

The serialised HTML is correct. It is the BROWSER that rewrites it ::

    with ui.card(href=f"/class/{target}"):     # renders an <a>
        ui.text(code)
        ui.link(label="workbook", href=...)    # an <a> inside an <a>

HTML forbids a nested anchor. The parser therefore closes the first
``<a>`` the moment it meets the second, and **everything that follows
lands outside** — out of the card, in the parent's flow.

Measured on ``examples/ecole`` on 2026-09-12: the card rendered 130 px of
nothing and the room's name appeared in the next hour's cell. No JS
error, no failed request, and ``TestClient`` returned exactly the right
document — the fault only exists after the parser. On screen, it does not
look like a structural flaw: it looks like a spacing problem, which sends
one looking in the wrong place.

What the rule reads
-------------------

A container that becomes an anchor — ``href=`` on a component that
renders an ``<a>`` — and, in its ``with`` body, a call that renders an
anchor in turn. Both families are **discovered** by the same criterion: a
component whose call carries an ``href=``. No table written here.

The sweep does not descend into a nested ``with`` that reopens an anchor:
the first level is enough, and the case has never come up.

⚠️ What the rule does NOT say
-----------------------------

That a computed ``href=`` is harmless. ``ui.card(href=x)`` counts,
whatever ``x``'s provenance: it is the PRESENCE of the parameter that
makes the anchor, not its value. A literal ``href=None``, by contrast,
does not — and it is read as such.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: The rule's name, as it appears in a finding.
RULE = "link-inside-a-link"


def _call_name(node: ast.expr) -> str | None:
    """``card`` for ``ui.card(...)``, ``link`` for ``ui.link(...)``."""
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _makes_an_anchor(call: ast.Call) -> bool:
    """Does the call carry an ``href=`` that is not literally null?

    ``href=None`` is written on purpose in this repository to say "no
    link here" (a tile that does not have its route yet). Reading it as
    an anchor would produce a finding on code that says precisely the
    opposite.
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
    """The anchors opened inside another anchor's body."""
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        outside = [
            item.context_expr
            for item in node.items
            if isinstance(item.context_expr, ast.Call)
            and _makes_an_anchor(item.context_expr)
        ]
        if not outside:
            continue
        outer = outside[0]
        for inner in _anchors_inside(node.body):
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=inner.lineno,
                    message=(
                        f"`{_call_name(inner)}` carries an `href=` inside "
                        f"`{_call_name(outer)}`, which carries one too — an "
                        f"`<a>` inside an `<a>`."
                    ),
                    hint=(
                        "HTML forbids it: the browser's parser CLOSES the "
                        "outer anchor on meeting the inner one, and "
                        "everything that follows leaves the container. The "
                        "serialised HTML stays correct, so no render test "
                        "sees it. Remove the `href=` from the container and "
                        "set TWO explicit links inside."
                    ),
                )
            )
    return findings
