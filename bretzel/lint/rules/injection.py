"""Rule: ``ui.html`` with anything but a literal.

``ui.html`` injects markup **verbatim, never escaped**. Its node has said
so forever (``core/tree.py``: *"every occurrence is a candidate XSS sink
and should be auditable"*), and the component is deliberately called
``ui.html`` and not ``ui.raw_html`` — a frightening name warns one
person, once, at the moment they write it.

What warns every time is a tool. In the framework's repository that is a
frozen list of calls (``test_ui_html_call_sites_are_listed``); for an
app, freezing makes no sense — but **judging literalness** does.

- ``ui.html("<hr>")`` → a literal, no path from user input: ignored.
- ``ui.html(article.body)`` → the value comes from elsewhere. Reported,
  because that is exactly the form that turns a database field into an
  executed script.

The rule does not claim to detect an XSS: it makes the choice
**visible**, so that it is taken rather than suffered. The constructor
already refuses a `ClientBinding` — making the runtime write markup from
client state would be a client-driven sink.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "non-literal-html"


def _is_literal(node: ast.expr) -> bool:
    """A literal, or a concatenation / f-string of literals only."""
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
                    "`ui.html(…)` receives a non-literal value: the markup "
                    "is injected verbatim, never escaped."
                ),
                hint=(
                    "Sanitise (bleach/nh3) first, or go through "
                    "`ui.markdown`, which escapes embedded HTML and rewrites "
                    "dangerous URLs. If the value is safe, say so in a "
                    "comment at the call site."
                ),
            )
        )
    return findings
