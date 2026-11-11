"""Rule: a kwarg passed to ``ui.*`` that the component does not accept.

**Why this rule still exists although the base layer refuses.** An
unknown kwarg that reached the DOM would be an inert attribute:
``ui.input(label="…")`` would render ``<input label="Display name">``,
with no label displayed at all.

The base layer **raises** (cf. ``attrs.py`` § declared escape
hatch), which makes this rule redundant… at runtime only. It keeps one
reason to exist, and it counts: **it sees without executing.** A
component in a branch never taken, a rarely rendered page, a path behind
an ``if`` — the base layer will only raise the day somebody goes through
there. The rule reads the call site, so it sees it straight away.

⚠️ It does NOT judge the anchor family (``href`` / ``target`` / ``rel`` /
``download``): those are declared raw attributes, legitimate with
``tag="a"``, and whether they land on a link depends on the rendered
tag. The render refuses a stray one
(``component._refuse_stray_anchor_attrs``), gated by
``test_a_link_attribute_lands_on_a_link``.

The rule is **pure**: it takes a module and the API index, it knows
neither corpus nor floor (cf. :mod:`bretzel.lint.corpus`).
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module, catalogue, derived
from bretzel.lint.report import Finding

RULE = "unknown-kwarg"

#: The raw HTML escape hatch is NOT redeclared here: it is read from the
#: base layer (:func:`bretzel.components.base.attrs.is_declared_raw_attr`),
#: which enforces it at runtime. One table, one
#: behaviour — otherwise the lint and the runtime would end up no longer
#: saying the same thing, and it is the lint one would believe.
#:
#: ``hx_`` is added here alone: the base layer refuses it (it only admits
#: the hyphenated form), so it would be reported as an unknown kwarg —
#: but :mod:`bretzel.lint.rules.transport` diagnoses it BETTER, by saying
#: what is really missing (the HMAC signature). One problem, one finding.
_TRANSPORT_PREFIXES = ("hx_", "hx-")

#: A sentinel: the symbol exists but cannot be judged here.
#:
#: A dedicated object, and not an empty ``frozenset()`` compared by
#: identity: CPython does not guarantee it will never intern the empty
#: frozenset, and a component accepting nothing would then become
#: indistinguishable from a helper — silently, in the direction that
#: reports NOTHING.
_NOT_JUDGED: object = object()


def _accepted(ui_name: str) -> frozenset[str] | object | None:
    """What ``ui.<name>`` accepts.

    ``None`` = the symbol does not exist. :data:`_NOT_JUDGED` = it exists
    but **we do not judge it**: the helpers (``ui.each``,
    ``ui.notification``, ``ui.column``…) have their own contract and
    raise by themselves on an unknown kwarg — running them through the
    catch-all's mill would produce false positives on those declaring
    ``**kwargs``, for no gain since they are not silent. The raw-HTML
    catch-all, by contrast, is a components matter.
    """
    return derived(f"{RULE}.accepted", _accepted_by_name).get(ui_name)


def _accepted_by_name() -> dict[str, frozenset[str] | object]:
    """:func:`_accepted` for every symbol, built once per pass."""
    from bretzel.introspect import RESERVED_KWARGS, ComponentInfo

    return {
        name: frozenset(
            {p.name for p in info.params}
            | set(RESERVED_KWARGS)
            | set(info.handler_kwargs)
            | set(info.named_slots)
        )
        # ``autofocus`` is reserved (the socle reads it) but refused where
        # the component declares no ``FOCUS_TARGET``: said here before run.
        - ({"autofocus"} if info.focus_target is None else set())
        if isinstance(info, ComponentInfo)
        else _NOT_JUDGED
        for name, info in catalogue().items()
    }


def _is_raw_attr(name: str) -> bool:
    from bretzel.components.base.attrs import (
        is_declared_raw_attr,
        is_passthrough_attr,
    )

    return (
        is_passthrough_attr(name)
        or is_declared_raw_attr(name)
        or name.startswith(_TRANSPORT_PREFIXES)
    )


def check(module: Module) -> list[Finding]:
    """The kwargs no component called here reads."""
    findings: list[Finding] = []
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ui"
        ):
            continue
        accepted = _accepted(func.attr)
        if accepted is None:
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=f"`ui.{func.attr}` does not exist.",
                    hint="`bretzel describe` lists the real surface.",
                )
            )
            continue
        if accepted is _NOT_JUDGED:
            continue
        for keyword in node.keywords:
            if not keyword.arg or _is_raw_attr(keyword.arg):
                continue
            if keyword.arg not in accepted:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=keyword.lineno,
                        message=(
                            f"`ui.{func.attr}({keyword.arg}=…)`: the "
                            f"component does not read this kwarg — it will go "
                            f"into the DOM as an inert attribute, with no "
                            f"error and no effect."
                        ),
                        hint=(
                            f"`bretzel describe {func.attr}` shows what it "
                            f"accepts; for a deliberate HTML attribute, "
                            f"`attrs={{...}}`."
                        ),
                    )
                )
    return findings
