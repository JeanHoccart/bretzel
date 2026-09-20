"""Layer 7 — the framework judges the code written against it.

The counterpart of :mod:`bretzel.introspect`: that one **describes**,
this one **reports**. The distinction is not cosmetic — it decides what
can be extracted. ``describe`` reflects the installed code, so it must
travel at its exact version, otherwise it lies; ``lint`` carries *rules*,
knowledge that depends on no version, and it is the half that can leave
the public repository one day. The ``lint-stays-extractable`` contract in
the ``.importlinter`` file makes that a mechanical guarantee rather than
an intention: no framework module outside ``cli`` may import this
package.

**Two tiers, by safety and not by convenience**:

- :func:`run` — static. AST only, **nothing of the app is executed**. It
  is the default, and it is what makes it safe to run over a third
  party's code.
- :func:`run_deep` — imports the application to query its map
  (undeclared routables, contract drift). Far more powerful, but it
  **runs the user's code**: it cannot be the default, and it takes not
  paths but a ``module:attribute`` target — the questions it asks have
  no answer in an isolated file.
"""

from __future__ import annotations

import inspect
from functools import cache
from pathlib import Path
from types import MappingProxyType

from bretzel.lint.corpus import bound as corpus_bound
from bretzel.lint.corpus import modules
from bretzel.lint.deep import lint_app, run_deep
from bretzel.lint.report import Finding, Report
from bretzel.lint.rules import STATIC

__all__ = (
    "Finding",
    "Report",
    "available_rules",
    "lint_app",
    "rule_summaries",
    "run",
    "run_deep",
)


def available_rules() -> tuple[str, ...]:
    """What the tool can verify. Enumerable by design: a `check` that
    cannot say what it covers cannot be judged."""
    return tuple(sorted(STATIC))


@cache
def rule_summaries() -> MappingProxyType[str, str]:
    """What each rule refuses, in one sentence — ITS OWN.

    The readable counterpart of :func:`available_rules`: that one says
    what is covered, this one says what against. Added on 2026-09-06 for
    the living documentation, which listed twelve bare names for want of
    being able to reach the sentence.

    **Read from the module carrying the rule, never copied here.** A
    hand-written summary drifts faster than it serves — this repository
    deleted a whole skill for that reason — and there is no reason to
    maintain a second version of a sentence that already exists at the
    head of the file.

    The ``Rule:`` prefix is dropped: it is a module-header convention,
    not part of the meaning. What remains reads after "it refuses …".
    """
    return MappingProxyType({
        slug: _stated_by(fn) for slug, fn in sorted(STATIC.items())
    })


def _stated_by(check: object) -> str:
    """The first non-empty line of a rule's module, cleaned up.

    The reStructuredText markup is dropped too. A public sentence is
    meant to be DISPLAYED — in a terminal, in a page — and ``some
    ``double backticks`` and **stars**`` read there as-is. The double
    backtick becomes a single one, which is the interface's convention;
    the stars disappear.
    """
    doc = (inspect.getdoc(inspect.getmodule(check)) or "").strip()
    line = next((li for li in doc.splitlines() if li.strip()), "")
    line = line.strip().removeprefix("Rule:").strip().rstrip(".")
    return line.replace("``", "`").replace("**", "")


def run(
    paths: list[Path] | tuple[Path, ...],
    *,
    rules: tuple[str, ...] | None = None,
) -> Report:
    """Run the static rules over the Python files under ``paths``.

    ``rules`` narrows the pass to a named subset. That is what a gate
    needs: it owns **one** prohibition and its corpus, and has no
    business turning red because a neighbouring rule found something
    else. An unknown name raises rather than being ignored — a selection
    that empties itself silently would return a green report.
    """
    if rules is not None:
        unknown = sorted(set(rules) - set(STATIC))
        if unknown:
            raise KeyError(
                f"unknown rule(s): {unknown}. Available: {list(available_rules())}."
            )
    selected = {name: check for name, check in STATIC.items() if rules is None or name in rules}
    found = modules(paths)
    report = Report(files_scanned=len(found), rules_run=tuple(sorted(selected)))
    # The corpus is exposed for the duration of the pass: a rule
    # reporting on one module may need to know what ANOTHER file
    # declares (cf. ``corpus.bound``). Bound here and nowhere else, so
    # the scope is exactly the call's.
    with corpus_bound(found):
        for module in found:
            for check in selected.values():
                report.findings.extend(check(module))
    report.findings.sort(key=lambda f: (f.path.as_posix(), f.line, f.rule))
    return report
