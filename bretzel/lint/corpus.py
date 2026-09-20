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
from pathlib import Path
from typing import Any, TypeVar

#: Folders we never descend into — neither app code, nor readable.
_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)


@dataclass(frozen=True)
class Module:
    """A source file and its tree, parsed once."""

    path: Path
    tree: ast.Module
    source: str


def discover(paths: list[Path] | tuple[Path, ...]) -> list[Path]:
    """The ``.py`` files under ``paths`` (files or folders)."""
    found: list[Path] = []
    for entry in paths:
        if entry.is_file():
            if entry.suffix == ".py":
                found.append(entry)
            continue
        for candidate in sorted(entry.rglob("*.py")):
            if _SKIP_DIRS.isdisjoint(candidate.parts):
                found.append(candidate)
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
# ``contextvars`` and not a module variable: the charter's anti-rule 2
# forbids mutable global state and explicitly allows registries scoped to
# a call. Unbound = an empty tuple, so a rule called outside ``run`` (a
# unit test) degrades cleanly instead of breaking.

_CORPUS: ContextVar[tuple[Module, ...]] = ContextVar("bretzel_lint_corpus", default=())


# The derivations that cost O(corpus) — computed ONCE per pass
# ───────────────────────────────────────────────────────────────────────────
#
# A rule reports on one module, but those reading ``current()`` compute
# the same thing for each of them. Without memoisation, ``run`` becomes
# quadratic: measured on 2026-08-27, ``value-outside-table`` re-walked the
# AST of ``examples/``'s 322 files for each of those 322 files, so
# **56 s** — on its own two thirds of the lint baseline, and ~110 s of a
# bare ``pytest``'s 230 s (it is paid twice: the rule alone, then the
# baseline).
#
# The memo lives in the BINDING, not in a global cache: its lifetime is
# exactly the pass's, so two ``run`` over two corpora cannot contaminate
# each other, and the charter's anti-rule 2 holds. Outside ``run`` (a rule
# called on its own in a unit test), there is no binding: we build without
# memoising rather than write into a default shared by every caller.
_DERIVED: ContextVar[dict[str, Any] | None] = ContextVar(
    "bretzel_lint_corpus_derived", default=None
)

_T = TypeVar("_T")


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


def derived(key: str, build: Callable[[], _T]) -> _T:
    """The corpus's ``key`` derivation, built once.

    ``build`` takes no argument: it must derive from the corpus exposed
    by :func:`current`, otherwise two callers under the same key would
    read each other's result. Outside ``run``, nothing is memoised —
    ``build`` is called every time, which keeps a rule correct when it is
    exercised on its own.
    """
    memo = _DERIVED.get()
    if memo is None:
        return build()
    if key not in memo:
        memo[key] = build()
    return memo[key]
