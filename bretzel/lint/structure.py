"""Notes: an app's structure, against ``app-structure.md``.

Two things the documented structure asks for, that nothing else in
``check`` reads:

- **a feature over ~400 lines is a folder** (``state.py``, ``logic.py``,
  ``ui.py``, ``feature.py``), not one file. The threshold is indicative,
  so it is a note, never a finding;
- **an app with features declares their contracts** (``Feature(name=,
  kind=, provides=, uses=)``). Without one, ``bretzel features`` has no
  map to print and ``bretzel impact`` cannot say what a change touches.

A note, not a rule, for the reason ``check --deep`` gives: an app with no
contract is not FAILED for it. It is told once, and goes on.

What counts as a feature module: a ``.py`` file directly in a
``features/`` folder, other than its ``__init__.py``. What counts as an
app: a module that calls ``Bretzel(...)``, with a ``features/`` folder
beside it among the files read — a throwaway mockup, alone in its
folder, is not an app with features.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

NOTE_LONG = "feature-too-long"
NOTE_NO_CONTRACT = "no-feature-contract"

#: ``app-structure.md`` § 4: "a folder beyond ~400 LOC".
FOLDER_ABOVE = 400


def notes(found: Sequence[Module]) -> list[Finding]:
    """The structure notes of a corpus, sorted like the findings."""
    out = [*_long_features(found), *_apps_without_contract(found)]
    out.sort(key=lambda f: (f.path.as_posix(), f.line, f.rule))
    return out


def is_feature_module(path: Path) -> bool:
    return path.parent.name == "features" and path.name != "__init__.py"


def _long_features(found: Sequence[Module]) -> list[Finding]:
    return [
        Finding(
            rule=NOTE_LONG,
            path=m.path,
            line=1,
            message=(
                f"the feature `{m.path.stem}` is {lines} lines in one file; "
                f"beyond ~{FOLDER_ABOVE} a feature is a folder."
            ),
            hint=(
                f"features/{m.path.stem}/ with feature.py (the contract), "
                f"state.py, logic.py (the handlers) and ui.py (the @page) — "
                f"app-structure.md § 4."
            ),
        )
        for m in found
        if is_feature_module(m.path)
        and (lines := len(m.source.splitlines())) > FOLDER_ABOVE
    ]


def _calls(module: Module, name: str) -> list[ast.Call]:
    return [
        node
        for node in module.nodes
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
    ]


def _apps_without_contract(found: Sequence[Module]) -> list[Finding]:
    out: list[Finding] = []
    for app in found:
        calls = _calls(app, "Bretzel")
        if not calls:
            continue
        root = app.path.parent
        features = [m for m in found if m.path.is_relative_to(root / "features")]
        if not features or any(_calls(m, "Feature") for m in features):
            continue
        out.append(
            Finding(
                rule=NOTE_NO_CONTRACT,
                path=app.path,
                line=calls[0].lineno,
                message=(
                    "this app has a `features/` folder and no `Feature` "
                    "contract in it: `bretzel features` has no map to "
                    "print, and `bretzel impact` cannot say what a change "
                    "touches."
                ),
                hint=(
                    "In each feature: feature = Feature(name=, kind=, "
                    "provides=[…], uses=[…]) — app-structure.md § 2."
                ),
            )
        )
    return out
