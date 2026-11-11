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
import importlib
import inspect
from typing import Any

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
        else _helper_arguments(name)
        for name, info in catalogue().items()
    }


def _closed_arguments(obj: Any) -> frozenset[str] | object:
    """The keyword arguments ``obj`` takes, when its signature says them
    all: a ``**kwargs`` that forwards somewhere is :data:`_NOT_JUDGED`. A
    ``**retired`` only exists to refuse (``ui.notification(variant=)``
    says to write ``color=``): it closes the signature, it opens nothing."""
    try:
        params = inspect.signature(obj).parameters.values()
    except (TypeError, ValueError):
        return _NOT_JUDGED
    if any(p.kind is p.VAR_KEYWORD and p.name != "retired" for p in params):
        return _NOT_JUDGED
    return frozenset(p.name for p in params
                     if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY))


def _helper_arguments(name: str) -> frozenset[str] | object:
    """A ``ui.*`` helper (``ui.each``, ``ui.notification``…) is judged on
    its signature. It raises by itself on an unknown kwarg — but only the
    day the line runs, and a handler or a rare branch may wait weeks."""
    from bretzel import ui

    return _closed_arguments(getattr(ui, name, None))


def _framework_names(module: Module) -> tuple[dict[str, Any], list[Finding]]:
    """What ``from bretzel… import`` binds in this module, and the names it
    asks for that do not exist — ``from bretzel.state import follow`` after
    ``follow`` was retired fails at import, a step this rule runs before."""
    bound: dict[str, Any] = {}
    findings: list[Finding] = []
    for node in module.nodes:
        if not (isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                and (node.module == "bretzel" or node.module.startswith("bretzel."))):
            continue
        try:
            source = importlib.import_module(node.module)
        except ImportError:
            findings.append(Finding(
                rule=RULE, path=module.path, line=node.lineno,
                message=f"`{node.module}` does not exist.",
                hint="`bretzel describe` lists the real surface.",
            ))
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            if hasattr(source, alias.name):
                bound[alias.asname or alias.name] = getattr(source, alias.name)
                continue
            try:
                importlib.import_module(f"{node.module}.{alias.name}")
            except ImportError:
                findings.append(Finding(
                    rule=RULE, path=module.path, line=node.lineno,
                    message=f"`{node.module}` has no `{alias.name}`: this import fails.",
                    hint=f"`bretzel describe {alias.name}` finds what it became, if it moved.",
                ))
    return bound, findings


def _framework_calls(module: Module, bound: dict[str, Any]) -> list[Finding]:
    """A keyword no framework callable reads: ``@refreshable(broadcast=…)``,
    ``Bretzel(texts=…)`` — each a ``TypeError`` at import, said here first."""
    findings: list[Finding] = []
    for node in module.nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in bound):
            continue
        accepted = _closed_arguments(bound[node.func.id])
        if accepted is _NOT_JUDGED:
            continue
        for keyword in node.keywords:
            if keyword.arg and keyword.arg not in accepted:  # type: ignore[operator]
                findings.append(Finding(
                    rule=RULE, path=module.path, line=keyword.lineno,
                    message=(f"`{node.func.id}({keyword.arg}=…)`: not one of its "
                             f"arguments — a TypeError when this line runs."),
                    hint=f"`bretzel describe {node.func.id}` shows what it takes.",
                ))
    return findings


def _is_component(ui_name: str) -> bool:
    from bretzel.introspect import ComponentInfo

    return isinstance(catalogue().get(ui_name), ComponentInfo)


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
    """The kwargs no component called here reads, the framework names
    imported that do not exist, and the keywords its callables refuse."""
    bound, findings = _framework_names(module)
    findings.extend(_framework_calls(module, bound))
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
        if not _is_component(func.attr):
            findings.extend(
                Finding(
                    rule=RULE, path=module.path, line=keyword.lineno,
                    message=(f"`ui.{func.attr}({keyword.arg}=…)`: not one of its "
                             f"arguments — it raises when this line runs."),
                    hint=f"`bretzel describe {func.attr}` shows what it takes.",
                )
                for keyword in node.keywords
                if keyword.arg and keyword.arg not in accepted  # type: ignore[operator]
            )
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
