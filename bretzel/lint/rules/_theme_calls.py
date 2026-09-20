"""Reading a literal ``Theme(components={…})`` — once only.

This is **not** a module of AST helpers, and the nuance decides what may
enter here: three rules — ``theme``, ``variant``, ``shape`` — ask the
tree the same question, "what does this file declare as a theme", and it
is that question that is shared. The other rules do not have it. A
grab-bag of helpers would attract exactly the coupling the rules' purity
protects.

Why the extraction
------------------
All three read the same thing with their own copy. ``_dict_items``
existed in **two different signatures** — three elements in ``theme`` and
``shape``, two in ``variant`` — and ``variant`` re-wrote the recognition
of the ``Theme`` name by hand. It was not yet a bug: all three said the
same thing. It was the pattern that precedes a bug, the same one
``theme_vocabulary`` closed on 2026-08-16 — two copies of a loop end up
no longer saying what the runtime says, and it is the lint one would have
believed.

What it does NOT give the rules
-------------------------------
Nothing they do not already have. No corpus, no floor, no exit code: only
tree reading, on the tree it is handed. The purity set out in the
package's docstring holds.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

#: The name a theme is built under. Recognised as a NAME, called
#: directly (``Theme(...)``) or through an attribute
#: (``bretzel.Theme(...)``): a static rule does not resolve imports, and
#: requiring a single form would refuse correct code.
THEME_CALLABLE = "Theme"


def called_name(call: ast.Call) -> str | None:
    """The name called, bare or as an attribute — ``None`` otherwise."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def dict_items(node: ast.expr) -> list[tuple[str, ast.expr, ast.expr]]:
    """The ``"literal": value`` entries of a literal dict.

    Returns ``(key, the key's node, the value's node)``: the key's node
    carries the line number, which a rule needs to locate its finding. A
    caller that does not want it ignores the middle element — that is
    cheaper than two signatures, which is the state we come from.

    Everything else — a ``**spread``, a computed key, a variable in place
    of the dict — is ignored without noise: the rule is static, and
    reporting what it cannot read would produce noise on correct code.
    """
    if not isinstance(node, ast.Dict):
        return []
    return [
        (key.value, key, value)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


def components_arg(call: ast.Call) -> ast.expr | None:
    """The ``components=`` of a call that looks like ``Theme(...)``.

    ``None`` when it is not a ``Theme``, or when it has no such keyword —
    a theme may override only its palette.
    """
    if called_name(call) != THEME_CALLABLE:
        return None
    for keyword in call.keywords:
        if keyword.arg == "components":
            return keyword.value
    return None


def component_maps(tree: ast.Module) -> Iterator[ast.expr]:
    """Every ``components={…}`` of this tree's ``Theme(...)``.

    A module may carry several — one theme per screen, a test theme
    beside the real one. Returning them all rather than the first is what
    keeps a rule from judging on half a file.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            components = components_arg(node)
            if components is not None:
                yield components
