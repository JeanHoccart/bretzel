"""Rule: a component bent with ``!`` classes.

The silence it closes
---------------------

A ``!`` on a component's class reads as a fix and is none::

    ui.button("", variant="ghost", on_click=...,
              classes="size-full! min-w-0 p-0! rounded-field!")

The app's class already wins without it (the merge, below). What the
``!`` does is freeze the class against everything else — a variant, a
state, a theme — and hide what the call really does: the component is a
different one wearing its name. A clickable surface is
``ui.card(on_click=...)``, not a button forced that way.

What the rule reads
-------------------

A ``ui.*`` call — not a layout primitive, whose classes ARE its style —
whose ``classes=`` or ``slots=`` carry an important token, in either of
Tailwind's spellings: ``p-0!`` and ``!p-0``, after variants too
(``hover:!bg-text/5``). The value is read where it is spelled: at the
call, or in a module-level constant the call names
(``slots=CARDS`` with ``CARDS = {"header": "!p-4"}``).

Why it has no exception
-----------------------

The app's class wins without ``!``: the framework
removes from the theme's classes every utility the app redeclares, in
the same variant scope (:mod:`bretzel.theme.class_merge`). A ``!`` is
therefore useless — and if a class does not win without it, that is a
defect of Bretzel, to be reported, not an exception to write next to
the call. The rule used to spare a ``!`` explained by a comment (the
sidebar's ``h-screen`` held in a box, a ``ui.viewport`` held in a demo):
the merge settles both, so the comment door is closed.

Layout primitives (``ui.flex``, ``ui.vstack``…) are not read: their
classes ARE their style. The framework's own code never calls ``ui.*``
with classes, its themes being dicts the rule does not read.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import (
    LAYOUT_PRIMITIVES,
    keyword,
    literal_tokens,
    module_constants,
    slot_tokens,
    ui_name,
)
from bretzel.theme.class_merge import split_token

RULE = "component-forced-with-important"



def _forced(token: str) -> bool:
    """Important in any spelling: ``p-0!``, ``!p-0``, ``hover:!p-0``, and
    v3's ``!hover:p-0`` — the token is not its scope and utility without
    the ``!``."""
    scope, utility = split_token(token)
    return bool(utility) and f"{scope}{utility}" != token


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    constants = module_constants(module.tree)
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        name = ui_name(node)
        if name is None or name in LAYOUT_PRIMITIVES:
            continue
        forced = [f"`{t}`" for t in literal_tokens(keyword(node, "classes"), constants)
                  if _forced(t)]
        forced += [f"`{t}` (slot `{slot}`)"
                   for slot, t in slot_tokens(keyword(node, "slots"), constants)
                   if _forced(t)]
        if not forced:
            continue
        findings.append(Finding(
            rule=RULE,
            path=module.path,
            line=node.lineno,
            message=(f"`ui.{name}` forced with {', '.join(forced)} — useless: "
                     "the app's class already wins over the component's."),
            hint=("Drop the `!`. If the class then loses, it is a defect of Bretzel, "
                  "to report — not an exception to write. If the call redraws the "
                  "component (`ui.card` with no border, no shadow), the component "
                  "made for it may exist: `ui.card(on_click=..., hoverable=True)`, "
                  "a row of a list is `ui.card(variant=\"ghost\", active=...)`, "
                  "a pill is `ui.badge`."),
        ))
    return findings
