"""Rule: a zone listening on behalf of a NESTED zone.

The silence it closes
---------------------

Nothing breaks, and that is worse than a failure: **it works, ten times
too expensively**. ::

    @refreshable(deps=[TraceDraft])
    def trace_dialog() -> None:          # reads TraceDraft: that is its life
        ...

    @refreshable(deps=[PlanView, PlanRev, TraceDraft])
    def plan_panel() -> None:
        ...                              # never reads TraceDraft
        trace_dialog()                   # …but calls the one that does

``TraceDraft`` is a dialog's draft, and the dialog is **already a zone**:
it refreshes by itself. Declaring it on the parent means *"when the
dialog opens, redraw the whole panel"*.

Measured on ``examples/ecole`` on 2026-09-12: opening "Trace the room" —
setting a boolean to true — cost **679 ms and 15 451 bytes**, because the
response contained the whole room, every seat, every drag thumbnail and
the waiting list. Without the one dependency too many: **20 ms and 3 094
bytes**. Thirty times less, for the same screen.

What makes the fault easy to commit: the dialog is WRITTEN in the parent
zone's body, so declaring its dependency in the same place looks
coherent. The form does not remind you that the child is autonomous.

What the rule requires — the THREE conditions
---------------------------------------------

1. the zone declares ``X`` in its ``deps=``;
2. **its body never reads ``X``**, neither directly nor through an
   ordinary module helper (the sweep follows the calls);
3. **a zone it CALLS reads ``X``**.

⚠️ **The third condition is not a refinement, it is the rule.** Without
it, the finding falls on the repository's most common pattern: a REVISION
TOKEN. A database write touches no typed state, so nothing refreshes; the
documented remedy is an ``AppState`` counter (``ContactsRev``,
``PlanRev``) one increments on the write and declares as a dependency —
**and which nobody ever reads**. Measured over ``examples/``: the
"declared and not read" version produced about thirty findings, and they
were all that pattern. A rule that condemns the recommended idiom does not
measure what it thinks it does.

⚠️ What the rule does NOT say
-----------------------------

That a parent zone must never share a dependency with its child. If it
READS it too, both are right — it is condition 2 that settles it, and it
reads off the code.

It does not see beyond the module: a nested zone imported from elsewhere
is not recognised as a zone, so the case is silent rather than wrong.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: The rule's name, as it appears in a finding.
RULE = "zone-listening-too-widely"

_MARKS = frozenset({"refreshable"})

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _decorator_call(func: _Func) -> ast.Call | None:
    for deco in func.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        target = deco.func
        name = (
            target.attr
            if isinstance(target, ast.Attribute)
            else target.id
            if isinstance(target, ast.Name)
            else None
        )
        if name in _MARKS:
            return deco
    return None


def _declared_deps(call: ast.Call) -> list[ast.Name]:
    for kw in call.keywords:
        if kw.arg == "deps" and isinstance(kw.value, ast.List | ast.Tuple):
            return [e for e in kw.value.elts if isinstance(e, ast.Name)]
    return []


def _names_read(func: _Func) -> set[str]:
    """The names read in the BODY — decorators excluded.

    ⚠️ ``ast.walk`` over the function descends into its decorator list
    too, so every name in ``deps=[…]`` would be found there read by
    itself and the rule would be mute on 100 % of cases. Measured: it
    was, on its own textbook case.
    """
    return {
        n.id
        for stmt in func.body
        for n in ast.walk(stmt)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


def _reachable(
    start: _Func, functions: dict[str, _Func], zones: frozenset[str]
) -> tuple[set[str], set[str]]:
    """``(names read, zones called)`` from ``start``.

    The walk follows ordinary helpers and **stops at zones** — what a
    nested zone reads belongs to it. The zones met are returned
    separately: they are what decides the finding.
    """
    read_names: set[str] = set()
    children: set[str] = set()
    todo = [start]
    seen = {start.name}
    while todo:
        current = todo.pop()
        names = _names_read(current)
        read_names |= names
        for name in names:
            if name in zones and name != start.name:
                children.add(name)
                continue
            nxt = functions.get(name)
            if nxt is None or name in seen:
                continue
            seen.add(name)
            todo.append(nxt)
    return read_names, children


def check(module: Module) -> list[Finding]:
    """The dependencies a zone carries on another's behalf."""
    functions: dict[str, _Func] = {}
    zones: set[str] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions[node.name] = node
            if _decorator_call(node) is not None:
                zones.add(node.name)

    frozen = frozenset(zones)
    scope = {name: _reachable(functions[name], functions, frozen) for name in frozen}

    findings: list[Finding] = []
    for name in sorted(frozen):
        deco = _decorator_call(functions[name])
        if deco is None:  # pragma: no cover — `zones` le garantit
            continue
        read_names, children = scope[name]
        for dep in _declared_deps(deco):
            if dep.id in read_names:
                continue
            carriers = sorted(e for e in children if dep.id in scope[e][0])
            if not carriers:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=dep.lineno,
                    message=(
                        f"`{name}` declares `{dep.id}` without ever "
                        f"reading it, on behalf of `{carriers[0]}()` — which "
                        f"is a zone and already declares it."
                    ),
                    hint=(
                        "A nested zone refreshes by itself: the parent only "
                        "needs to follow the EFFECT, through a revision "
                        "token. The dependency too many does not RAISE and "
                        "does not show — it renders the whole zone on every "
                        "keystroke in the child (measured: 679 ms and 15 kB "
                        "instead of 20 ms and 3 kB). "
                        f"Remove `{dep.id}` from `{name}`'s `deps=`."
                    ),
                )
            )
    return findings
