"""Two live elements of a page never share an ``id`` — checked in dev.

An ``id`` written twice renders without a word. ``getElementById``, a
label's ``for=``, ``.open()`` / ``.set()``, an htmx target then reach the
FIRST element only — whichever the document order made it.

Checked on the page's final tree, not when a component is built: a page
may build a component a second time only to SHOW its HTML as text (the
playground does), and that copy never becomes a live element. For the same
reason the content of a ``<template>`` is skipped: it is inert until the
runtime clones it.

Dev only, like the other checks that read a whole page: an app that had a
harmless duplicate keeps serving in production, and sees it at its next
run in dev.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from bretzel.core.tree import Element, FragmentNode


def _live_ids(node: Any, found: dict[str, list[str]]) -> None:
    if isinstance(node, Element):
        if node.tag == "template":
            return
        ident = node.attrs.get("id")
        if isinstance(ident, str) and ident:
            found.setdefault(ident, []).append(node.tag)
        for child in node.children:
            _live_ids(child, found)
    elif isinstance(node, FragmentNode):
        for child in node.children:
            _live_ids(child, found)


def refuse_duplicate_ids(nodes: Iterable[Any]) -> None:
    """Raise if two live elements of ``nodes`` carry the same ``id``."""
    found: dict[str, list[str]] = {}
    for node in nodes:
        _live_ids(node, found)
    twice = {ident: tags for ident, tags in found.items() if len(tags) > 1}
    if not twice:
        return
    # Imported here: ``render`` does not reach up to the components at
    # load time (the error class lives with them).
    from bretzel.components.base.attrs import ComponentUsageError

    listed = "; ".join(
        f"id={ident!r} on {len(tags)} elements (<{'>, <'.join(tags)}>)"
        for ident, tags in sorted(twice.items())
    )
    zones = any(ident.startswith("refresh_") for ident in twice)
    raise ComponentUsageError(
        f"This page renders the same id twice: {listed}. getElementById, a "
        f"label's for=, .open() / .set() and htmx targets reach the first "
        f"one only.\n"
        f"  Give each element its own id=, or drop id= : the framework "
        f"names what it needs to find again."
        + (
            "\n  A `refresh_…` id is a @refreshable zone shown twice: zones "
            "built by one factory share their function's name — give each "
            "its own @refreshable(name=…)." if zones else ""
        )
    )
