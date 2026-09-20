"""Rule: a handler cannot be a lambda.

The framework addresses a handler by its ``module::qualname`` and
re-resolves it through ``sys.modules`` when the action arrives — that is
what lets the client carry only a signed identifier rather than a
reference. A lambda has no addressable name, so ``encode_handler_id``
**raises** (``HandlerError: Lambda handlers are forbidden``). Verified on
2026-08-16: lambda and closure refused, top-level function accepted.

So it is a **certain** failure, not a heuristic — and it shows
statically, before the app is even started. The form is natural to write
(``on_click=lambda: state.count + 1``) and that is precisely why it
deserves a rule: nothing in the syntax suggests it is forbidden.

⚠️ **Closures are NOT covered here**, although they are refused the same
way (``Closure handler 'make.<locals>.inner'``). Detecting them requires
resolving a name down to its definition and knowing whether it is nested
— a scope analysis this module does not do. The omission is declared
rather than silent: the lambda is the frequent case, the closure is still
caught at runtime with a clear message.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "lambda-handler"


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if not keyword.arg or not keyword.arg.startswith("on_"):
                continue
            if not isinstance(keyword.value, ast.Lambda):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=keyword.value.lineno,
                    message=(
                        f"`{keyword.arg}=lambda …`: the framework addresses "
                        f"a handler by its `module::qualname` and re-resolves "
                        f"it through `sys.modules`. A lambda has no "
                        f"addressable name — this raises at render time."
                    ),
                    hint=(
                        "Write a top-level function in the module and pass "
                        "it by name. To freeze an argument, "
                        "`functools.partial(handler, item_id)`."
                    ),
                )
            )
    return findings
