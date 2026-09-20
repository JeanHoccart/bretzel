"""Rule: an ``AppState`` total incremented without being declared additive.

The silence it closes
---------------------

``stats.views += 1`` reads 5, computes 6, and the commit sends "set 6".
Two requests that read 5 both send "set 6": one is missing. Declaring
``field(default=0, merge="add")`` sends the DELTA instead, which the
store applies itself — and both count.

Nothing reports the omission. Measured on 2026-09-04: alone in front of
their screen, a developer NEVER meets it, because their requests are
sequential — each reads what the previous one wrote. It takes two tabs
clicking together, or two users. The fault therefore waits for
production, and there it does not raise either: a counter simply advances
more slowly than the clicks.

Why ``AppState`` ONLY
---------------------

Because ``+=`` does not mean "total". ``state.page += 1`` is a CHOICE —
"the next page" — and declaring it additive would produce page 7 when two
tabs go to 3 and to 5. The signal is therefore not the operator, it is
the **sharing**: an ``AppState`` is unique for the whole process, so a
number one increments there is a collective count, never somebody's
position.

The other scopes are deliberately OUT of the rule, and not because they
are safe:

- ``SessionState`` and ``UserState`` are shared between the tabs of one
  browser, so the loss is real there — but a "+ 1" there is as often a
  pagination or a setting as a total, and reporting both would make noise
  where the rule must make signal;
- ``PageState`` only lives for the duration of a render; two quick clicks
  on the same page can overlap, but what is lost there dies with the tab.

Measured over ``examples/`` on 2026-09-05: 45 increments on an
``AppState``, 4 on a session, 2 on a page. The scope that matters is also
the one where the pattern is most frequent.

What the rule cannot see
------------------------

A state passed as an ARGUMENT (``def bump(s: Stats): s.views += 1``): it
would take real data flow. The detector goes one notch up — it knows
direct constructions (``Stats().views += 1``) and local variables
assigned from a state (``s = Stats()``), which covers both of the
repository's spellings. Saying so here rather than letting exhaustiveness
be assumed.

The rule is **pure**: one module, some findings. It knows neither corpus
nor floor.
"""

from __future__ import annotations

import ast
from functools import lru_cache

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "undeclared-shared-counter"

#: The operations that ACCUMULATE. ``*=`` and the rest are not: their
#: delta depends on the value read, so additivity would not save them.
_ACCUMULATORS = (ast.Add, ast.Sub)


@lru_cache(maxsize=1)
def _app_state_names() -> frozenset[str]:
    """The public ``AppState`` classes, derived and not copied.

    A hand-written table of names drifts from the code it judges — that
    is the folder's rule.
    """
    import inspect

    import bretzel
    import bretzel.state as state_module
    from bretzel.state.scopes.server import ServerState

    names = set()
    for module in (bretzel, state_module):
        for name in dir(module):
            obj = getattr(module, name, None)
            if (
                inspect.isclass(obj)
                and issubclass(obj, ServerState)
                and getattr(obj, "__scope__", None) == "app"
            ):
                names.add(name)
    return frozenset(names)


def _base_names(node: ast.ClassDef) -> set[str]:
    """The base names written, ``module.Class`` reduced to ``Class``."""
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _local_app_states(tree: ast.Module) -> dict[str, dict[str, ast.expr | None]]:
    """``{app class: {field: its declaration's value}}``.

    We keep the whole declaration and not only the name: it is what will
    say whether ``merge="add"`` is already there. The classes are read in
    file order, so a local base is known before its children.
    """
    known = _app_state_names()
    states: dict[str, dict[str, ast.expr | None]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not (_base_names(node) & (known | set(states))):
            continue
        fields: dict[str, ast.expr | None] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields[stmt.target.id] = stmt.value
        states[node.name] = fields
    return states


def _declares_add(value: ast.expr | None) -> bool:
    """Does the declaration carry ``merge="add"``?"""
    if not isinstance(value, ast.Call):
        return False
    return any(
        kw.arg == "merge"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value == "add"
        for kw in value.keywords
    )


def _state_of(target: ast.Attribute, bound_locals: dict[str, str]) -> str | None:
    """The state class behind ``X.field``, or ``None``.

    Two spellings, and they are the repository's: ``Stats().views``
    (direct construction) and ``s.views`` where ``s`` comes from an
    ``s = Stats()`` higher up in the same function.
    """
    holder = target.value
    if isinstance(holder, ast.Call) and isinstance(holder.func, ast.Name):
        return holder.func.id
    if isinstance(holder, ast.Name):
        return bound_locals.get(holder.id)
    return None


def _locals_bound_to_a_state(func: ast.AST, known: set[str]) -> dict[str, str]:
    """``{local name: state class}`` for the function's ``s = Stats()``."""
    bound: dict[str, str] = {}
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name):
            continue
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id in known:
                bound[target.id] = value.func.id
        # ``await Stats.load()`` — the other way in
        elif isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
            call = value.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "load"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id in known
            ):
                bound[target.id] = call.func.value.id
    return bound


def check(module: Module) -> list[Finding]:
    """The ``AppState`` totals incremented without an additive declaration."""
    states = _local_app_states(module.tree)
    if not states:
        return []
    known = set(states)

    findings: list[Finding] = []
    for func in ast.walk(module.tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound_locals = _locals_bound_to_a_state(func, known)
        for node in ast.walk(func):
            if not isinstance(node, ast.AugAssign):
                continue
            if not isinstance(node.op, _ACCUMULATORS):
                continue
            if not isinstance(node.target, ast.Attribute):
                continue
            cls_name = _state_of(node.target, bound_locals)
            if cls_name not in states:
                continue
            field_name = node.target.attr
            if field_name not in states[cls_name]:
                continue
            if _declares_add(states[cls_name][field_name]):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`{cls_name}.{field_name}` is incremented in "
                        f"place, and `{cls_name}` is an `AppState` — so ONE "
                        f"object for the whole server. The field is not "
                        f"declared additive: two requests reading the same "
                        f"number write the same number, and one increment is "
                        f"lost."
                    ),
                    hint=(
                        f"Declare `{field_name}: … = field(default=0, "
                        f'merge="add")`. The commit will send the DELTA, '
                        f"which the store applies itself — two simultaneous "
                        f"clicks will both count. If this number is NOT a "
                        f"total but a position or a setting, leave it as-is: "
                        f"the last writer is then right."
                    ),
                )
            )
    return findings
