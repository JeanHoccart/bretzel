"""core/scope — logic: WHAT a task worked on.

A ``kind="logic"`` feature: no state, no resource, one question.

Why this was the missing measurement
-------------------------------------
The first version judged every task by the same yardstick. Flagged by the
user on 2026-09-12: "it is normal that creating/modifying the framework
takes time, what I want to evaluate is your performance on the APPS".

They are right, and the mixture made the figure useless in both
directions: building a layer of the base requires reading the whole base
and verifying often — that is healthy work counting as back-and-forth.
Conversely, an app written with the framework should demand almost
nothing: the surface is ASKED FOR (`describe`), the contract is DECLARED
(`Feature`), and the lint judges before anything is launched. If an app
task costs fifteen cycles, it is the framework that is not keeping its
promise — or me not using it.

That is the distinction we want to see, and it did not exist.

A task's scope
---------------
That of its WRITES, not its reads: reading the base layer to write an app
is normal, and counting reads would make every app task look like
framework work. With no write, we fall back on the reads — a task that
only read still has a subject.

⚠️ Two things are NOT a subject, and counting them as one was measured
wrong on 2026-09-12:

- **what a command SEARCHES for**. A ``grep``'s pattern is a needle, not
  a target: ``grep -rln "examples/ecole" .`` sweeps the whole repository.
  Without this distinction, the task that DELETED an app was filed
  INSIDE that app — it is the "no, I prefer crm" line, which raised the
  question;
- **the scratch work**. Writing a throwaway script in the scratchpad is a
  MEANS of working on something else. It won anyway, by sheer count:
  **178 tasks out of 276** filed as "scratch" had a real subject in their
  own writes (79 the base layer, 62 the suites, 26 the docs). So it now
  only wins if it is alone, and it stays visible in that case, because a
  task that touched ONLY throwaways did indeed deliver nothing elsewhere.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from bretzel import Feature

FRAMEWORK = "framework"
TESTS = "tests"
DOC = "doc"
SCRATCH = "scratch"
OTHER = "other"

#: An app's prefix: ``app:crm``, ``app:atelier``. Kept readable rather
#: than coded, because it is shown as is in a filter.
APP = "app:"

LABELS = {
    FRAMEWORK: "the base layer — `bretzel/`",
    TESTS: "the suites and the gates",
    DOC: "the reference and the tracking",
    SCRATCH: "the sandbox, outside the repo",
    OTHER: "unattributed",
}

#: What follows the repository root in an absolute path. We cut THERE
#: rather than look for a named segment: the repository folder is itself
#: called ``bretzel``, so looking for "bretzel" in an absolute path
#: catches the root and files the whole tree as framework. Measured: the
#: first version returned 6 728 "framework" writes out of 5 580 write
#: calls, which was impossible and should have shown.
ROOT = re.compile(r"^.*?[/\\]bretzel[/\\]", re.IGNORECASE)

#: A scratch path: the session scratchpad, a temporary. They are not in
#: the repository and say nothing about the work delivered.
OUTSIDE_REPO = re.compile(
    r"(?:^|[/\\])(?:Temp|tmp|scratchpad|AppData)(?:[/\\]|$)", re.IGNORECASE
)


def relative(path: str) -> str:
    """The path reduced to the repository root, separators normalised."""
    cleaned = path.strip().strip("'\"").replace("\\", "/")
    rootless = ROOT.sub("", cleaned.replace("/", "\\")).replace("\\", "/")
    return rootless.lstrip("./")


def scope_of(path: str) -> str:
    """ONE path's scope — ``""`` if the path says nothing.

    The empty string and not ``OTHER``: a call with no path must not
    weigh in the dominant-scope vote. Confusing them would make "other"
    win on every task that launches many commands.
    """
    if not path:
        return ""
    if OUTSIDE_REPO.search(path):
        return SCRATCH
    rel = relative(path)
    if not rel or ("/" not in rel and "." not in rel):
        return ""
    segments = rel.split("/")
    head = segments[0]
    if head == "examples" and len(segments) > 1:
        return f"{APP}{segments[1]}"
    if head == "bretzel":
        return FRAMEWORK
    if head == "tests":
        return TESTS
    if head in (".claude", "docs") or rel.endswith(".md"):
        return DOC
    return ""


#: What a command SEARCHES for: the search tool's name, its flags, then
#: the pattern. We cut the pattern — and only it, the rest of the command
#: keeps its real targets (``--include``, the folder swept).
NEEDLE = re.compile(
    r"\b(?:grep|egrep|fgrep|rg|findstr|Select-String)\b"
    r"(?:\s+-{1,2}[\w-]+(?:=\S+)?)*"
    r"\s+(?P<pattern>'[^']*'|\"[^\"]*\"|\S+)"
)


def without_needles(command: str) -> str:
    """The command without the search patterns it carries."""
    return NEEDLE.sub(
        lambda m: m.group(0)[: m.start("pattern") - m.start(0)], command
    )


#: The paths a command quotes. Wide enough to catch a
#: ``sed -n 1,50p examples/crm/main.py`` as well as an absolute ``Write``.
PATHS = re.compile(r"[\w./\\:-]*[/\\][\w./\\-]+\.\w+|examples[/\\][\w-]+")


def scopes_in(command: str) -> list[str]:
    """Every scope a command touches, duplicates included.

    The duplicates count: a command naming three app files weighs more
    than one naming a single file, and that is what we want.
    """
    target = without_needles(command)
    return [s for s in (scope_of(m) for m in PATHS.findall(target)) if s]


def dominant(scopes: Iterable[str]) -> str:
    """The scope that wins — ``OTHER`` if nothing stands out.

    The most frequent, with no threshold: a task touching the base layer
    AND an app is filed on the side where it wrote most, and that is the
    right arbitration for the question asked. The strip, for its part,
    keeps the detail.

    ⚠️ One exception, and only one: the scratch work does not take part
    in the vote. It is a means, not a subject — a throwaway script
    written to measure the base layer speaks about the base layer. It
    only comes out if it is the sole candidate, and that case does say
    something true.
    """
    counts = Counter(s for s in scopes if s)
    if not counts:
        return OTHER
    subjects = [(s, n) for s, n in counts.items() if s != SCRATCH]
    if subjects:
        return max(subjects, key=lambda item: item[1])[0]
    return SCRATCH


def is_app(scope: str) -> bool:
    """Is this an APPLICATION task? That is the user's question."""
    return scope.startswith(APP)


def label(scope: str) -> str:
    """The scope spelled out — for a ROW, not a cell.

    ``the base layer — bretzel/``, ``the suites and the gates``. It is
    what one wants when a whole row is devoted to it, as on the phases
    screen.
    """
    if is_app(scope):
        return f"app {scope[len(APP):]}"
    return LABELS.get(scope, scope)


def short(scope: str) -> str:
    """The scope in one word — for a CELL.

    ⚠️ Both exist because they do not serve the same place, and
    confusing them shows: "the sandbox, outside the repo" in a table
    badge wraps onto two lines and makes the rows unequal — measured on
    screen, heights from 50 to 100 px in the same table.
    """
    return scope[len(APP):] if is_app(scope) else scope


feature = Feature(
    name="scope",
    kind="logic",
    provides=[scope_of, scopes_in, dominant, is_app, label, short],
)
