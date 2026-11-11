"""Rule: a component bent with ``!`` classes.

The silence it closes
---------------------

``!`` wins over the component's own classes, so it works — once::

    ui.button("", variant="ghost", on_click=...,
              classes="size-full! min-w-0 p-0! rounded-field!")

The component is then a different one wearing its name: its size, its
padding, its corner are no longer the framework's, a theme no longer
reaches them, and a fix of the component no longer reaches the app. A
clickable surface is ``ui.card(on_click=...)``, not a button forced that
way.

What the rule reads
-------------------

A ``ui.*`` call — not a layout primitive, whose classes ARE its style —
whose literal classes carry a token ending in ``!``.

⚠️ What the rule does NOT say
-----------------------------

That ``!`` is never needed: overriding a theme's own fixed value (the
sidebar's ``h-screen`` in a constrained mount, cf. ``traps.md``; a
``ui.viewport``, ``fixed`` by design, held in a demo's box) is one. The
rule asks it to SAY so: a comment on the call — on a line of it, or the
line just above — spares it. An unexplained ``!`` is the finding.
"""

from __future__ import annotations

import ast
import io
import tokenize

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import keyword, literal_tokens, ui_name

RULE = "component-forced-with-important"

_PRIMITIVES = {"flex", "hstack", "vstack", "grid", "container"}


def _comment_lines(module: Module) -> set[int]:
    """The lines carrying a real comment — read by ``tokenize``: a ``#``
    inside a string (a colour, ``"#fff"``) is not one."""
    found: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(module.source).readline):
            if token.type == tokenize.COMMENT:
                found.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return found
    return found


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    comments: set[int] | None = None
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        name = ui_name(node)
        if name is None or name in _PRIMITIVES:
            continue
        forced = [t for t in literal_tokens(keyword(node, "classes")) if t.endswith("!")]
        if not forced:
            continue
        if comments is None:
            comments = _comment_lines(module)
        # Explained: a comment on a line of the call, or the line above.
        if any(n in comments for n in range(node.lineno - 1, (node.end_lineno or node.lineno) + 1)):
            continue
        findings.append(Finding(
            rule=RULE,
            path=module.path,
            line=node.lineno,
            message=(f"`ui.{name}` forced with {', '.join(f'`{t}`' for t in forced)} — "
                     "the component no longer has its own size, padding or corner."),
            hint=("Use the component made for it (a clickable surface is "
                  "`ui.card(on_click=..., hoverable=True)`, a pill `ui.badge`), or say "
                  "on the line which theme value the override must beat."),
        ))
    return findings
