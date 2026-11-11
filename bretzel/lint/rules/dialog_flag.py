"""Rule: a dialog opened by a boolean of server state.

The silence it closes
---------------------

Nothing breaks. The dialog opens, a little later::

    class NewCalendar(PageState):
        open: bool = field(default=False)

    def open_new() -> None:
        NewCalendar().open = True          # a request, a render

    @refreshable
    def new_dialog() -> None:
        if not NewCalendar().open:
            return
        with ui.dialog(open=True, ...):     # drawn by the server, to open

Every opening is a round trip for a thing the server never reads: the
dialog knows whether it is open.

What the rule reads
-------------------

A ``ui.dialog`` / ``ui.drawer`` whose ``open=`` is ``True`` or a boolean
field of a server state (``PageState`` & co.) of the module, in a function
that reads that boolean — when that state carries NOTHING but booleans.

A state that carries anything else is spared: a key (``key: str``), the
element aimed at (``pupil_id``), the values typed into the form and kept
across a refused submit. That dialog must know WHICH element, or what was
written, and it is the server's to draw; its ``open: bool`` is the
switch of a draft, not a window's own state.

⚠️ What the rule does NOT say
-----------------------------

That every ``open=True`` is wrong: a dialog opened by the server after a
gesture it alone sees (a drop to confirm) is legitimate — its state
carries a key or a payload, which is what the rule spares.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import keyword, ui_name

RULE = "dialog-opened-by-a-server-flag"

_SERVER = {"PageState", "SessionState", "UserState", "AppState", "ServerState"}
_OVERLAYS = {"dialog", "drawer"}


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _flags(module: Module) -> dict[str, set[str]]:
    """Server-state class that carries ONLY booleans → those fields.

    One field of another type (a key, an id, a typed value) and the class
    is a draft: the server needs it to draw the dialog, so it is left out.
    """
    found: dict[str, set[str]] = {}
    for node in module.nodes:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(_base_name(b) in _SERVER for b in node.bases):
            continue
        fields = [stmt for stmt in node.body
                  if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)]
        if fields and all(isinstance(f.annotation, ast.Name) and f.annotation.id == "bool"
                          for f in fields):
            found[node.name] = {f.target.id for f in fields}
    return found


def _flag_of(node: ast.expr, flags: dict[str, set[str]], holders: dict[str, str]) -> str | None:
    """``Class.field`` when ``node`` IS ``Class().field`` (or ``holder.field``
    for a variable holding ``Class()``) for one of the flags."""
    if not isinstance(node, ast.Attribute):
        return None
    owner = node.value
    cls = None
    if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name):
        cls = owner.func.id
    elif isinstance(owner, ast.Name):
        cls = holders.get(owner.id)
    if cls in flags and node.attr in flags[cls]:
        return f"{cls}.{node.attr}"
    return None


def check(module: Module) -> list[Finding]:
    flags = _flags(module)
    if not flags:
        return []
    # ONE pass over the shared nodes (cf. test_lint_derives_the_corpus_once):
    # the functions' spans, the variables holding a state, the reads of a
    # flag and the overlays, tied together afterwards by their lines.
    functions: list[tuple[int, int]] = []
    holders: dict[str, str] = {}
    attributes: list[ast.Attribute] = []
    overlays: list[ast.Call] = []
    for node in module.nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.lineno, node.end_lineno or node.lineno))
        elif (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id in flags):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    holders[target.id] = node.value.func.id
        elif isinstance(node, ast.Attribute):
            attributes.append(node)
        elif isinstance(node, ast.Call) and ui_name(node) in _OVERLAYS:
            overlays.append(node)
    reads = [(a.lineno, flag) for a in attributes
             if (flag := _flag_of(a, flags, holders)) is not None]

    findings: list[Finding] = []
    for call in overlays:
        opened = keyword(call, "open")
        literal = isinstance(opened, ast.Constant) and opened.value is True
        direct = _flag_of(opened, flags, holders) if opened is not None else None
        if not literal and direct is None:
            continue
        spans = [(a, b) for a, b in functions if a <= call.lineno <= b]
        if not spans:
            continue
        first, last = max(spans)  # the innermost function
        flag = direct or next((f for line, f in reads if first <= line <= last), None)
        if flag is None:
            continue
        findings.append(Finding(
            rule=RULE,
            path=module.path,
            line=call.lineno,
            message=(f"`ui.{ui_name(call)}` is opened by `{flag}`, a boolean of "
                     "server state — a request and a render to open a window."),
            hint=("Open it by its imperative API: `box = ui.dialog(...)`, then "
                  "`on_click=box.open()`; a form closes it with "
                  "`on_submit=[action, box.close()]`. Keep a server state only for "
                  "what the server needs to draw it (which element, the values typed)."),
        ))
    return findings
