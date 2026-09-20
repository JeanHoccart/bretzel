"""Rule: a cast that erases a state value's PROVENANCE.

The silence it closes, reported by the user on 2026-08-25
---------------------------------------------------------
"I have to refresh the page to refresh the stepper." The CRM's import
screen stayed stuck on its first panel: you clicked "Check", the server
state did move to the next step, the rest of the zone re-rendered — and
the stepper did not budge. Only an F5 put the two back in agreement.
Worse: after "Start over", the screen stayed on the last step while the
state had gone back to zero.

One single line was the cause ::

    ui.stepper(value=int(draft.step), clickable=False)
                     ^^^^

The mechanism
-------------
A client-state component (stepper, tabs, accordion, the five pickers, the
four overlays…) keeps its current value in a JavaScript signal, not in
the DOM. The morph of a ``@refreshable`` zone **deliberately preserves**
the existing element — that is what makes an open menu or a field being
typed into survive a refresh triggered elsewhere on the page. The signal
is not re-read.

So the component has to say "my value comes from the server, re-adopt it
after the morph" — the ``_serverSync`` marker (cf.
``components/base/_wiring.server_sync_marker``). And it only emits it
**if** it can see the value comes from the server: a state field arrives
STAMPED (``_BoundInt`` / ``_BoundStr``…, set by
``state/scopes/server._stamp``), a literal does not.

``int(draft.step)`` returns an ordinary Python integer. The stamp is
lost, the component concludes "client value", and emits nothing.

⚠️ **And it cannot be caught at runtime.** At that point the component
only sees an ``int``, indistinguishable from a perfectly legitimate
``value=1`` — which must precisely NOT be re-adopted, otherwise a
neighbouring refresh would send the user back to where the server thinks
they are. The only place where the information still exists is the
**source code**. Hence this rule, and not a runtime guard.

Measured in the browser, the same page with and without the cast ::

    after Next        panel 1        panel 2
    after Next x2     panel 1        panel 3
    after F5          panel 3        panel 3
    after Start over  panel 3        panel 1

What the rule covers, and what it leaves
----------------------------------------
It targets the **two-way props** (``ComponentInfo.two_way``, 30
components) — the exact population where a client signal holds the value
and can diverge from the server. A cast on a text slot
(``ui.badge(label=str(n))``) is harmless: there is no signal to re-adopt,
the morph replaces the node.

It requires the argument to be an **attribute or subscript access**
(``draft.step``, ``prefs["x"]``) — so plausibly a state read. ``int(3)``
is useless but harmless, and a rule that reports the harmless ends up
unread.

It sees **three** forms since 2026-08-30, not one — the cast, the ``or``
and the f-string. The up-to-date inventory is in :func:`stripping_expr`,
which IS the detector; what follows says what stays out.

⚠️ **This paragraph described the opposite until 2026-09-01.** It
enumerated "what it does NOT see: an f-string, arithmetic, a
``state.x or default``" — written before the widening, and left as-is
afterwards, fifty lines from a ``stripping_expr`` that handles them. It
is this repository's most expensive docstring shape: it contradicts
itself in the same file, and the false half is the one read first.

**What stays OUT**, measured and deliberate: arithmetic. Its three sites
in the repository all operate on literals (``'A' * 200``), so harmless.
Widening to "any non-trivial expression" would be maximal and probably
noisy.

**The licit side is paid for**: ``bretzel check examples`` returns 12
findings over 321 files, of which **zero** from this rule — the three
watched forms produce no false positive on the real corpus.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "state-lost-by-a-cast"

#: The language's coercions. They all return a NEW object, so they all
#: lose the stamp — there is no exception to sort out.
_CASTS = frozenset({"int", "str", "float", "bool", "list", "tuple", "set", "dict"})


def _two_way(ui_name: str) -> frozenset[str]:
    """The two-way props of ``ui.<ui_name>``, or the empty set.

    Read from introspection rather than copied: the list derives from
    ``reactive_prop(writes=True)``, so a prop that becomes bidirectional
    between here and the base layer cannot leave the rule silently.
    """
    from bretzel.introspect import ComponentInfo, describe_ui_symbol, ui_symbol_names

    if ui_name not in ui_symbol_names():
        return frozenset()
    info = describe_ui_symbol(ui_name)
    if not isinstance(info, ComponentInfo):
        return frozenset()
    return frozenset(info.two_way)


def _reads_state(node: ast.expr) -> bool:
    """Does ``node`` look like a state read — ``a.b`` or ``a["b"]``?

    An accepted heuristic, the same one as from the start: it is what
    keeps ``int(3)`` from counting. The lint does not have typing, it has
    shape.
    """
    return isinstance(node, ast.Attribute | ast.Subscript)


def _first_state_read(node: ast.expr) -> ast.expr | None:
    """The first state read under ``node``, or ``None``."""
    return next(
        (sub for sub in ast.walk(node) if _reads_state(sub)),  # type: ignore[misc]
        None,
    )


def stripping_expr(value: ast.expr) -> tuple[str, str] | None:
    """``(form, read's source)`` when ``value`` erases the provenance.

    Isolated from the sweep so that the bite proof attacks it directly,
    on fabricated expressions, rather than on a fake repository.

    **Three forms, widened on 2026-08-30** — the cast was only the first
    one found, not the only one that erases:

    - ``CAST(state.x)`` — returns a bare ``int`` / ``str``. The original
      form, four measured sites, all fixed;
    - ``state.x or default`` — **the most treacherous**, and that is why
      it is in: ``a or b`` returns the operand AS-IS, so the stamp
      survives when the value is truthy and vanishes when it is falsy.
      The component resynchronises half the time, depending on the data —
      and a bench that only tries the filled case declares it good;
    - ``f"{state.x}"`` — always erases, like the cast. Zero sites measured
      today, included because it is of the same order and free.

    ⚠️ What stays OUT, and deliberately: arithmetic. Swept over the 18
    apps on 2026-08-25, its three sites all operate on literals
    (``'A' * 200``) — harmless. Widening to "any non-trivial expression"
    would be maximal and probably noisy; measuring the licit side is what
    found this repository's only two gate bugs.
    """
    if isinstance(value, ast.Call):
        if not (isinstance(value.func, ast.Name) and value.func.id in _CASTS):
            return None
        if len(value.args) != 1 or value.keywords:
            return None
        if not _reads_state(value.args[0]):
            return None
        return f"{value.func.id}(…)", ast.unparse(value.args[0])

    if isinstance(value, ast.BoolOp):
        lu = _first_state_read(value)
        if lu is None:
            return None
        word = "or" if isinstance(value.op, ast.Or) else "and"
        return f"… {word} …", ast.unparse(lu)

    if isinstance(value, ast.JoinedStr):
        lu = _first_state_read(value)
        if lu is None:
            return None
        return 'f"…"', ast.unparse(lu)

    return None


def check(module: Module) -> list[Finding]:
    """The casts set on a two-way prop."""
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ui"
        ):
            continue
        props = _two_way(func.attr)
        if not props:
            continue
        for keyword in node.keywords:
            if keyword.arg not in props:
                continue
            stripped = stripping_expr(keyword.value)
            if stripped is None:
                continue
            shape, inner = stripped
            # ``or`` only erases INTERMITTENTLY: the operand is returned
            # as-is, so the stamp survives when the value is truthy. That
            # is what makes it more dangerous than a cast, not less — the
            # message has to say so, otherwise "it works sometimes" reads
            # as "it does not matter".
            when = (
                " — and only when the value is falsy, so the component "
                "resynchronises half the time depending on the data"
                if shape.endswith("or …") else ""
            )
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`ui.{func.attr}({keyword.arg}={shape})` : "
                        f"the expression erases `{inner}`'s provenance{when}, "
                        f"so the component will not know the value comes from "
                        f"the server and will not re-adopt it after a "
                        f"refresh."
                    ),
                    hint=(
                        f"Pass the bare value: `{keyword.arg}={inner}`. If "
                        f"formatting is needed, it goes in the state (a "
                        f"validator, a computed field), not at the call "
                        f"site."
                    ),
                )
            )
    return findings
