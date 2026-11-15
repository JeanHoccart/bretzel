"""Note: a component redrawn call after call — a variant may be missing.

Why a note and not a rule
-------------------------

Since the app's class wins over the theme's
(:mod:`bretzel.theme.class_merge`), overriding a component is easy, and
silent: nothing marks any more an app that draws its cards again at
every call, as the ``!`` used to. A redraw is not a fault — but the
same redraw three times is a look the app has given a name to without
saying it, and that look belongs in a ``variant=`` or in the app's
``Theme(components=…)``, where a fix reaches every call.

So ``bretzel check`` COUNTS, and says it once per component. A note
does not fail the command: a finding would make the app put a ``!``
back, or worse, to silence it.

What is counted
---------------

The **drawing**: background, border, shadow, ring, corner, text colour
and size, font, and the padding of a slot that is not the root. The
**placement** — width, height, flex, alignment, outer margin, position —
is not: placing a component in its page is what an app's classes are
for (``choisir-etat-et-composant.md``).

Only a class that REDRAWS counts: one whose properties the component's
theme already sets on that slot. Giving a border to a component that
has none is a choice; replacing its border is a redraw.

The threshold: the same component, the same family, in three calls — or
in a ``slots=`` / ``classes=`` constant that two calls share, which is
the redraw already named, one step from a variant.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Iterator, Sequence
from functools import cache
from pathlib import Path

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
from bretzel.theme.class_merge import (
    longhands,
    slot_strings,
    split_token,
    utility_properties,
)

NOTE = "component-redrawn"

#: Calls redrawing the same family of the same component before the note.
THRESHOLD = 3


def _family(longhand: str, *, root: bool) -> str | None:
    """The drawing family a longhand belongs to; ``None`` for placement."""
    if longhand == "background-color":
        return "background"
    if longhand.endswith("-radius"):
        return "corner"
    if longhand.startswith("border-") or longhand == "--tw-border-style":
        return "border"
    if longhand.startswith("--tw-shadow"):
        return "shadow"
    if longhand.startswith("--tw-ring"):
        return "ring"
    if longhand in {"color", "font-size"}:
        return "text"
    if longhand in {"font-weight", "font-family", "letter-spacing"}:
        return "font"
    if longhand.startswith("padding-") and not root:
        return "padding"
    return None


def _families(tokens: Sequence[str], *, root: bool) -> dict[tuple[str, str], str]:
    """``(scope, longhand) → family`` for the drawing ``tokens`` set."""
    found: dict[tuple[str, str], str] = {}
    for token in tokens:
        scope, utility = split_token(token)
        props = utility_properties(utility)
        for longhand in longhands(props) if props else ():
            family = _family(longhand, root=root)
            if family:
                found[(scope, longhand)] = family
    return found


@cache
def _theme_draws(name: str, slot: str) -> frozenset[tuple[str, str]]:
    """``(scope, longhand)`` the shipped theme of ``ui.<name>`` draws on
    ``slot`` — its template, and the rows of its variants and sizes."""
    from bretzel import ui

    theme = getattr(getattr(ui, name, None), "THEME", None)
    if not isinstance(theme, dict):
        return frozenset()
    tokens = " ".join(slot_strings(theme, slot)).split()
    return frozenset(_families(tokens, root=slot == "root"))


def _overrides(call: ast.Call, name: str,
               constants: dict[str, ast.expr]) -> Iterator[tuple[str, str | None]]:
    """``(family, shared constant or None)`` for each family the call redraws."""
    for kwarg in ("classes", "slots"):
        value = keyword(call, kwarg)
        if value is None:
            continue
        shared = value.id if isinstance(value, ast.Name) and value.id in constants else None
        pairs = ([("root", t) for t in literal_tokens(value, constants)] if kwarg == "classes"
                 else slot_tokens(value, constants))
        by_slot: dict[str, list[str]] = defaultdict(list)
        for slot, token in pairs:
            by_slot[slot].append(token)
        for slot, tokens in by_slot.items():
            drawn = _theme_draws(name, slot)
            for key, family in _families(tokens, root=slot == "root").items():
                if key in drawn:
                    yield family, shared


def notes(found: Sequence[Module]) -> list[Finding]:
    """One note per component redrawn past the threshold, at its first call."""
    calls: dict[str, dict[str, set[tuple[Path, int]]]] = defaultdict(lambda: defaultdict(set))
    shared: dict[tuple[str, Path, str], set[int]] = defaultdict(set)
    for module in found:
        constants = module_constants(module.tree)
        for node in module.nodes:
            if not isinstance(node, ast.Call):
                continue
            name = ui_name(node)
            if name is None or name in LAYOUT_PRIMITIVES:
                continue
            for family, constant in _overrides(node, name, constants):
                calls[name][family].add((module.path, node.lineno))
                if constant:
                    shared[(name, module.path, constant)].add(node.lineno)
    shared_names = {name for (name, _p, _c), lines in shared.items() if len(lines) >= 2}
    result: list[Finding] = []
    for name, by_family in sorted(calls.items()):
        flagged = sorted(family for family, sites in by_family.items()
                         if len(sites) >= THRESHOLD or name in shared_names)
        if not flagged:
            continue
        sites = sorted(set().union(*(by_family[f] for f in flagged)))
        path, line = sites[0]
        result.append(Finding(
            rule=NOTE,
            path=path,
            line=line,
            message=(f"`ui.{name}` redrawn in {len(sites)} calls ({', '.join(flagged)}) — "
                     "is a variant missing?"),
            hint=("Name the look once: a `variant=` the component offers, or "
                  f"`Theme(components={{\"{name}\": ...}})` for the whole app. If neither "
                  "fits, it may be a variant Bretzel lacks."),
        ))
    return result
