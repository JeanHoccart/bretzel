"""Rule: a ``Topic`` wired on one side only.

A topic read by a function that nothing writes leaves its zones frozen; a
topic written but read by nothing redraws nothing. Neither raises: the page
renders, and it just never changes. Reading across the whole corpus is what
tells them apart, so this module also gives ``bretzel features`` its map of
who reads and writes each topic.

A write is a ``@writes(TOPIC)`` or a ``refresh(TOPIC)``, including one in a
``for topic in (A, B): refresh(topic)``. A topic handed around as an argument
is out of reach: it would take real data flow.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bretzel.lint.corpus import Module, current, derived
from bretzel.lint.report import Finding

RULE = "topic-half-wired"

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class TopicUses:
    """Where one topic is declared, and the functions touching it."""

    path: Path
    line: int
    readers: set[str] = field(default_factory=set)
    writers: set[str] = field(default_factory=set)


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _declared(found: Sequence[Module]) -> dict[str, TopicUses]:
    topics: dict[str, TopicUses] = {}
    for module in found:
        for stmt in module.tree.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and isinstance(stmt.value, ast.Call)
                and _name(stmt.value.func) == "Topic"
            ):
                topics[stmt.targets[0].id] = TopicUses(module.path, stmt.lineno)
    return topics


def _aliases(module: Module) -> dict[str, str]:
    """``{local name: original name}`` for ``from x import A as B``."""
    return {
        alias.asname: alias.name
        for node in module.nodes
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname
    }


def _loops(func: ast.AST) -> dict[str, list[ast.expr]]:
    """``{loop variable: what it walks}`` for a ``for`` over a literal."""
    return {
        node.target.id: list(node.iter.elts)
        for node in ast.walk(func)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and isinstance(node.iter, (ast.Tuple, ast.List))
    }


def _note(
    topics: dict[str, TopicUses], aliases: dict[str, str], expr: ast.expr, side: str, label: str
) -> None:
    name = _name(expr)
    name = aliases.get(name, name) if name else None
    if name in topics:
        getattr(topics[name], side).add(label)


def topics_in(found: Sequence[Module]) -> dict[str, TopicUses]:
    """Every topic declared in ``found``, with what reads and writes it."""
    topics = _declared(found)
    if not topics:
        return {}

    for module in found:
        aliases = _aliases(module)
        for func in module.nodes:
            if not isinstance(func, _FUNCTIONS):
                continue
            for decorator in func.decorator_list:
                if isinstance(decorator, ast.Call):
                    kind = _name(decorator.func)
                    if kind in ("reads", "writes"):
                        side = "readers" if kind == "reads" else "writers"
                        for arg in decorator.args:
                            _note(topics, aliases, arg, side, func.name)
            loops = _loops(func)
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and _name(node.func) == "refresh" and node.args:
                    arg = node.args[0]
                    walked = loops.get(arg.id, [arg]) if isinstance(arg, ast.Name) else [arg]
                    for expr in walked:
                        _note(topics, aliases, expr, "writers", func.name)
    return topics


def check(module: Module) -> list[Finding]:
    """The topics declared here that one side of the app never touches."""
    uses = derived(f"{RULE}.uses", lambda: topics_in(current()))
    findings: list[Finding] = []
    for name, use in uses.items():
        if use.path != module.path or (use.readers and use.writers):
            continue
        if use.readers:
            message = (
                f"`{name}` is read by {', '.join(sorted(use.readers))}, and nothing "
                f"writes it: the zones reading it never redraw."
            )
            hint = f"Add `@writes({name})` on the functions that change this data."
        elif use.writers:
            message = (
                f"`{name}` is written by {', '.join(sorted(use.writers))}, and nothing "
                f"reads it: no zone redraws."
            )
            hint = f"Add `@reads({name})` on the functions that read this data."
        else:
            message = f"`{name}` is declared, and nothing reads or writes it."
            hint = "Attach the functions that touch this data, or remove the topic."
        findings.append(
            Finding(rule=RULE, path=module.path, line=use.line, message=message, hint=hint)
        )
    return findings
