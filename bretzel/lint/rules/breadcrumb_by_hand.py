"""Rule: a breadcrumb built by hand — ``ui.breadcrumb`` exists.

The silence it closes
---------------------

::

    ui.link("Lieux", href="/reglages/lieux")
    ui.text("› Dispositions", color="muted")

It reads like a breadcrumb, but it is not one: no ``nav``, no
``aria-current``, another separator, another size.

What the rule reads
-------------------

A ``ui.text`` / ``ui.link`` whose literal text STARTS with a typographic
breadcrumb separator (``›``, ``»``) followed by a space. Not ``/`` nor
``>``: ``ui.text("/ month")`` is a price and ``"/ 280"`` a counter.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import first_text, ui_name

RULE = "breadcrumb-built-by-hand"

_SEPARATORS = ("› ", "» ")


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in module.nodes:
        if not (isinstance(node, ast.Call) and ui_name(node) in {"text", "link"}):
            continue
        text = first_text(node)
        if text is None or not text.lstrip().startswith(_SEPARATORS):
            continue
        findings.append(Finding(
            rule=RULE,
            path=module.path,
            line=node.lineno,
            message=(f"`ui.{ui_name(node)}({text.strip()[:30]!r})` draws a breadcrumb's "
                     "separator by hand."),
            hint=("Write `with ui.breadcrumb(): ui.breadcrumb_item(label=..., href=...)` "
                  "— one item per level, the last without `href`."),
        ))
    return findings
