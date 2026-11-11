"""Discovering an app's files, and their AST — **with no floor**.

That is what makes the tool portable, and it deserves writing down: the
124 gates in ``tests/consistency/`` fuse *the rule* with *THIS
repository's corpus and its non-vacuity floor* (``EXAMPLES_FLOOR`` and
friends). A gate is right to do so — it protects a known corpus. A tool
aimed at **any app** cannot: it knows nothing of the expected size.

Hence the split: here we discover and parse, never judging the
population. The floors stay on the gates' side, which become
**consumers** of this module on their own corpus.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bretzel.introspect import ComponentInfo, HelperInfo

#: Folders we never descend into — neither app code, nor readable. Also
#: skipped: a folder whose name starts with a dot (``.git``, ``.claude``,
#: a tool's cache) and a virtual environment whatever its name, known by
#: its ``pyvenv.cfg`` (PEP 405). ``bretzel/theme/build.py`` copies these
#: rules, plus a root-level ``archive``, for the Tailwind scan.
_SKIP_DIRS = frozenset(
    {"__pycache__", "venv", "site-packages", "node_modules", "build", "dist"}
)


@dataclass(frozen=True)
class Module:
    """A source file and its tree, parsed once."""

    path: Path
    tree: ast.Module
    source: str

    @cached_property
    def nodes(self) -> tuple[ast.AST, ...]:
        """Every node of the tree, in ``ast.walk`` order — walked once and
        shared by the rules, which iterate this rather than ``tree``."""
        return tuple(ast.walk(self.tree))


def discover(paths: list[Path] | tuple[Path, ...]) -> list[Path]:
    """The ``.py`` files under ``paths`` (files or folders).

    The skipped folders are pruned BELOW a given folder, never the folder
    itself: ``bretzel check .claude/tool`` or a project checked out under
    ``~/build/`` is read as asked.
    """
    found: list[Path] = []
    for entry in paths:
        if entry.is_file():
            if entry.suffix == ".py":
                found.append(entry)
            continue
        below: list[Path] = []
        for root, dirs, files in entry.walk():
            dirs[:] = [
                d
                for d in dirs
                if d not in _SKIP_DIRS
                and not d.startswith(".")
                and not (root / d / "pyvenv.cfg").is_file()
            ]
            below.extend(root / f for f in files if f.endswith(".py"))
        found.extend(sorted(below))
    return found


def parse(path: Path) -> Module | None:
    """Parse a file, or return ``None`` when it is unreadable.

    Read as ``utf-8-sig``: a BOM had taken a file out of seven of this
    repository's gates for months, and the failure was silent. A file that
    does not parse is not a lint finding — it is a syntax error the
    interpreter will report far better than we can.
    """
    try:
        source = path.read_text(encoding="utf-8-sig")
        return Module(path=path, tree=ast.parse(source), source=source)
    except (OSError, SyntaxError, ValueError):
        return None


def modules(paths: list[Path] | tuple[Path, ...]) -> list[Module]:
    """Everything readable under ``paths``, parsed."""
    return [m for m in (parse(p) for p in discover(paths)) if m is not None]


# ───────────────────────────────────────────────────────────────────────────
# The pass's corpus — for the rare rules that cannot judge on their own
# ───────────────────────────────────────────────────────────────────────────
#
# A rule reports on ONE module, and that is what keeps it pure and
# testable. One single question escapes that frame:
# ``ui.button(variant="brand")`` is correct **if** a
# ``Theme(components={"button": {"variants": {"brand": …}}})`` exists —
# and that theme nearly always lives in ANOTHER file. Without the corpus,
# the rule would condemn the documented escape hatch for deviating from
# the shipped theme, that is to say precisely the form we recommend.
#
# ``contextvars`` and not a module variable: the framework
# forbids mutable global state and explicitly allows registries scoped to
# a call. Unbound = an empty tuple, so a rule called outside ``run`` (a
# unit test) degrades cleanly instead of breaking.

_CORPUS: ContextVar[tuple[Module, ...]] = ContextVar("bretzel_lint_corpus", default=())


# What is fixed for a pass — derived ONCE, not once per module
# ───────────────────────────────────────────────────────────────────────────
#
# A rule reports on one module, but those reading ``current()`` compute
# the same thing for each of them. Without memoisation, ``run`` becomes
# quadratic: ``value-outside-table`` would re-walk the AST of every file
# of the corpus for each of those files.
#
# The memo lives in the BINDING, not in a global cache: its lifetime is
# exactly the pass's, so two ``run`` over two corpora cannot contaminate
# each other. Outside ``run`` (a rule
# called on its own in a unit test), there is no binding: we build without
# memoising rather than write into a default shared by every caller.
_DERIVED: ContextVar[dict[str, Any] | None] = ContextVar(
    "bretzel_lint_corpus_derived", default=None
)


@contextmanager
def bound(found: Sequence[Module]) -> Iterator[None]:
    """Expose ``found`` as the current pass's corpus."""
    token = _CORPUS.set(tuple(found))
    memo_token = _DERIVED.set({})
    try:
        yield
    finally:
        _DERIVED.reset(memo_token)
        _CORPUS.reset(token)


def current() -> tuple[Module, ...]:
    """The pass's corpus, or an empty tuple outside ``run``."""
    return _CORPUS.get()


def derived[T](key: str, build: Callable[[], T]) -> T:
    """The pass's ``key`` derivation, built once.

    ``build`` takes no argument: it must derive from what is fixed for the
    pass — the corpus exposed by :func:`current`, or the installed
    framework — otherwise two callers under the same key would read each
    other's result. Outside ``run``, nothing is memoised — ``build`` is
    called every time, which keeps a rule correct when it is exercised on
    its own.
    """
    memo = _DERIVED.get()
    if memo is None:
        return build()
    if key not in memo:
        memo[key] = build()
    return memo[key]


def catalogue() -> dict[str, ComponentInfo | HelperInfo]:
    """``ui.<name>`` → its introspected card, read once per pass — the
    rules consult it for every module or every ``ui.*`` call."""
    from bretzel.introspect import describe_components

    return derived(
        "introspect.catalogue",
        lambda: {info.ui_name: info for info in describe_components()},
    )
