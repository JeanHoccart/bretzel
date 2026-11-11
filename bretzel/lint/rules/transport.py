"""Rule: an app does not drive the transport by hand.

The charter (CLAUDE.md, principle 2) keeps the transport boundary
runtime-only. An app declares an ``on_<event>=`` handler and the base
layer emits the **signed** POST (HMAC + timestamp + client-state
snapshot) through ``action_attrs``. Writing an ``hx-post`` by hand
produces a request that has none of that: it will be refused, or worse,
it will bypass a protection one believed was in place.

Two forms, because both reach the DOM:

- the ``hx_post=…`` kwarg — the base layer has a declared passthrough for
  ``hx-``, so it goes out verbatim and **does not raise**;
- the ``attrs={"hx-post": …}`` key — same path, different spelling.

One form is NOT transport: ``hx-trigger`` on a call that declares an
``on_<event>=`` handler. The request is still the base layer's, signed;
only WHEN it fires changes — ``"click, intersect"`` turns a "Load more"
button into an infinite scroll. Flagging it would say "the request will
go out without the signature", which is false. Without a handler, an
``hx-trigger`` starts nothing of the framework's: still flagged.

Nor is ``hx-boost="false"``: it sends nothing, it TAKES a link out of the
boost (a CSV download must be a real navigation).

A few framework components drive the swap engine directly, and that is
accepted: the list is frozen in
``tests/consistency/test_raw_htmx_stays_in_the_allowlist.py``, with the
charter's rule — "a new component that needed it must first push the
usage into a runtime helper". **That permission is the framework's, not
the apps'**: an app has no helper to write, it has a handler to declare.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "hand-written-transport"

_HINT = (
    "Declare `on_<event>=my_handler`: the base layer sets the `hx-post` "
    "with its HMAC signature. A hand-written POST has none."
)


def _hx_name(raw: str) -> str | None:
    """``hx_post`` / ``hx-post`` → ``hx-post``. Sinon ``None``."""
    normalised = raw.replace("_", "-")
    return normalised if normalised.startswith("hx-") else None


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        handled = any(k.arg and k.arg.startswith("on_") for k in node.keywords)

        def transport(attr: str, value: ast.expr, *, handled: bool = handled) -> bool:
            if handled and attr == "hx-trigger":
                return False
            opt_out = isinstance(value, ast.Constant) and value.value in ("false", False)
            return not (attr == "hx-boost" and opt_out)

        for keyword in node.keywords:
            if (keyword.arg and (attr := _hx_name(keyword.arg))
                    and transport(attr, keyword.value)):
                findings.append(_finding(module, keyword.value.lineno, attr))
            if keyword.arg == "attrs" and isinstance(keyword.value, ast.Dict):
                for key, value in zip(keyword.value.keys, keyword.value.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and (attr := _hx_name(key.value))
                        and transport(attr, value)
                    ):
                        findings.append(_finding(module, key.lineno, attr))
    return findings


def _finding(module: Module, line: int, attr: str) -> Finding:
    return Finding(
        rule=RULE,
        path=module.path,
        line=line,
        message=(
            f"`{attr}` written by hand: the request will go out WITHOUT "
            f"the HMAC signature nor the protocol headers the base layer "
            f"adds."
        ),
        hint=_HINT,
    )
