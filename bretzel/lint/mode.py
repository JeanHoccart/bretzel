"""Note: an app that writes its ``mode=`` in ``Bretzel(...)``.

The mode belongs to the launch command, not to the code: ``bretzel dev``
runs dev, a plain ``uvicorn main:app`` runs prod (``BRETZEL_MODE``,
``prod`` by default). Written in the call, it overrides both, in both
directions:

- ``mode="dev"`` keeps the app in dev wherever it runs: the browser CSS
  compiler, the unminified runtime and ``no-store`` on every load
  (measured on Orga: DOMContentLoaded 496 ms in dev against
  305 ms in prod), and the exception details in the responses;
- ``mode="prod"`` makes ``bretzel dev`` run a production app — no
  diagnostics while writing.

A note, not a finding: ``mode=`` is a public, documented setting, and a
benchmark that pins its mode on purpose is not at fault. What is noted is
only a LITERAL string — a value read from the environment
(``mode=os.environ.get(...)``) is the command deciding, through another
name. Tests are spared: a test pins its conditions, that is its job.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

NOTE_MODE = "mode-written-in-the-app"


def is_test_module(path: Path) -> bool:
    """A test file, or anything under a ``tests`` folder (benches, e2e apps)."""
    return (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name == "conftest.py"
    )


def _written_modes(module: Module) -> list[tuple[int, str]]:
    """``(line, value)`` of each literal ``mode=`` given to ``Bretzel(...)``."""
    out: list[tuple[int, str]] = []
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else "")
        if name != "Bretzel":
            continue
        for kw in node.keywords:
            if (kw.arg == "mode" and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)):
                out.append((kw.value.lineno, kw.value.value))
    return out


def notes(found: Sequence[Module]) -> list[Finding]:
    """One note per literal ``mode=`` in an app's ``Bretzel(...)`` call."""
    return [
        Finding(
            rule=NOTE_MODE,
            path=m.path,
            line=line,
            message=(
                f'`mode="{value}"` is written in the app: it overrides the '
                f"launch command, so the app runs in {value} however it is "
                f"started."
            ),
            hint=(
                "Remove `mode=`: `bretzel dev main:app` runs dev, "
                "`uvicorn main:app` runs prod (`BRETZEL_MODE`, prod by "
                "default). For `python main.py` with `app.run(reload=True)`, "
                "set `BRETZEL_MODE=dev` in the environment."
            ),
        )
        for m in found
        if not is_test_module(m.path)
        for line, value in _written_modes(m)
    ]
