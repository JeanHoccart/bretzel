"""What the app-idiom rules share: reading a ``ui.*`` call and its classes.

Four rules read the same two things — which ``ui.*`` component a call
makes, and the literal tokens of its ``classes=`` — so they read them
here, once, the same way.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping

#: The layout primitives: their classes ARE their style, so the rules
#: that judge a component bent by its classes do not read them.
LAYOUT_PRIMITIVES = frozenset({"flex", "hstack", "vstack", "grid", "container"})


def ui_name(call: ast.Call) -> str | None:
    """``badge`` for ``ui.badge(...)``; None for anything not ``ui.*``."""
    func = call.func
    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == "ui"):
        return func.attr
    return None


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def module_constants(tree: ast.Module) -> dict[str, ast.expr]:
    """``{NAME: value}`` for the module's top-level ``NAME = value`` (and
    ``NAME: T = value``) — the last one wins, as at run time."""
    found: dict[str, ast.expr] = {}
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)):
            found[stmt.targets[0].id] = stmt.value
        elif (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                and stmt.value is not None):
            found[stmt.target.id] = stmt.value
    return found


def literal_tokens(
    value: ast.expr | None, constants: Mapping[str, ast.expr] | None = None,
) -> list[str]:
    """The class tokens a ``classes=`` value spells out literally — the
    constant parts of an f-string included, the computed parts left out.

    Given ``constants`` (:func:`module_constants`), a bare name is read
    through its module-level value; without them, a name is computed."""
    if value is None:
        return []
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value.split()
    if isinstance(value, ast.JoinedStr):
        text = "".join(
            part.value for part in value.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
        return text.split()
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        return literal_tokens(value.left, constants) + literal_tokens(value.right, constants)
    if isinstance(value, ast.Name) and constants and value.id in constants:
        # Without the name: a constant spelled from itself reads once.
        rest = {k: v for k, v in constants.items() if k != value.id}
        return literal_tokens(constants[value.id], rest)
    return []


def slot_tokens(
    value: ast.expr | None, constants: Mapping[str, ast.expr] | None = None,
) -> list[tuple[str, str]]:
    """``(slot, token)`` for each class token a ``slots=`` value spells out:
    a dict literal, its ``**`` unpackings, a module-level name for either."""
    if isinstance(value, ast.Name) and constants and value.id in constants:
        rest = {k: v for k, v in constants.items() if k != value.id}
        return slot_tokens(constants[value.id], rest)
    if not isinstance(value, ast.Dict):
        return []
    found: list[tuple[str, str]] = []
    for key, item in zip(value.keys, value.values, strict=True):
        if key is None:
            found.extend(slot_tokens(item, constants))
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            found.extend((key.value, t) for t in literal_tokens(item, constants))
    return found


def first_text(call: ast.Call) -> str | None:
    """The literal start of a call's first positional argument."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr) and arg.values:
        head = arg.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return None
