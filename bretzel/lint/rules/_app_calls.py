"""What the app-idiom rules share: reading a ``ui.*`` call and its classes.

Four rules read the same two things — which ``ui.*`` component a call
makes, and the literal tokens of its ``classes=`` — so they read them
here, once, the same way.
"""

from __future__ import annotations

import ast


def ui_name(call: ast.Call) -> str | None:
    """``badge`` for ``ui.badge(...)``; None for anything not ``ui.*``."""
    func = call.func
    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == "ui"):
        return func.attr
    return None


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def literal_tokens(value: ast.expr | None) -> list[str]:
    """The class tokens a ``classes=`` value spells out literally — the
    constant parts of an f-string included, the computed parts left out."""
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
        return literal_tokens(value.left) + literal_tokens(value.right)
    return []


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
