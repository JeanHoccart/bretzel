"""Rule: a pill built by hand — ``ui.badge`` exists.

The silence it closes
---------------------

It renders, and it looks almost right::

    with ui.flex(classes=f"{zone} rounded-field px-3 py-1 bg-(--bz-solid) "
                         "text-(--bz-on-solid)"):
        ui.text(code, weight="bold")

It is ``ui.badge(code, variant="solid", color=...)`` written again — with
its own height, padding and corner, so it drifts from the framework's
style and from every theme.

What the rule reads
-------------------

A layout primitive (``flex``, ``hstack``, ``vstack``, ``grid``) whose
literal classes paint a solid background (``bg-(--bz-solid)``) AND round
it AND pad it horizontally (``px-``): the three gestures of a pill. A
solid block with no padding — a dot, the bar of a board — is a drawing,
and spared.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import keyword, literal_tokens, ui_name

RULE = "badge-built-by-hand"

_PRIMITIVES = {"flex", "hstack", "vstack", "grid"}


def _is_pill(tokens: list[str]) -> bool:
    solid = any(t.startswith("bg-(--bz-solid)") for t in tokens)
    rounded = any(t.startswith("rounded") for t in tokens)
    padded = any(t.startswith("px-") for t in tokens)
    return solid and rounded and padded


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in module.nodes:
        if not (isinstance(node, ast.Call) and ui_name(node) in _PRIMITIVES):
            continue
        if not _is_pill(literal_tokens(keyword(node, "classes"))):
            continue
        findings.append(Finding(
            rule=RULE,
            path=module.path,
            line=node.lineno,
            message=(f"`ui.{ui_name(node)}` painted as a pill (solid background, "
                     "rounded, padded) — `ui.badge` is that component."),
            hint=("Write `ui.badge(label, variant=\"solid\", color=...)`: `color` takes "
                  "the palette's names, and the badge keeps the framework's height, "
                  "padding and corner under every theme."),
        ))
    return findings
