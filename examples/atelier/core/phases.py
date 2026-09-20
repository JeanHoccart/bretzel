"""core/phases — logic: which work PHASE a call belongs to.

A ``kind="logic"`` feature: it renders nothing, touches no resource, and
carries no state. It answers one question and one only — "this tool call,
is it reading, writing, verifying or delivering?" — and everything else
in the workshop follows from that answer.

Why the phases are the heart
-----------------------------
Counting the calls says a task was expensive. It does not say WHY. The
sequence of phases, on the other hand, reads at a glance:

    RRRR WWWW VV WW VV                    → healthy
    R W V W V W V W V W V W V W V         → the endless back-and-forth

Both tasks may have the same number of calls. Only the second shows
somebody coding by trial and error, writing three lines, re-running the
suite, re-reading the red, rewriting three lines. That is exactly what
the user asked to see.

⚠️ The classification is HEURISTIC, and it stays so
---------------------------------------------------
A ``Bash`` call can do anything: ``cat`` reads, ``pytest`` verifies, a
``python - <<EOF`` writes a file. So we read the COMMAND, not only the
tool's name — and ambiguous cases will remain, filed as ``OTHER`` rather
than guessed. An invented phase would make the strip lie, and the strip
is all we look at.

The count of `OTHER` is shown: if it grows, it is the heuristic that
needs fixing, not the measurement that should be believed.
"""

from __future__ import annotations

import re

from bretzel import Feature

#: The four phases, in the order a healthy task goes through them. The
#: fifth — ``OTHER`` — is not a work phase: it is the admission that the
#: heuristic did not know.
READING = "reading"
WRITING = "writing"
VERIFYING = "verifying"
DELIVERING = "delivering"
OTHER = "other"

PHASES = (READING, WRITING, VERIFYING, DELIVERING, OTHER)

#: What each phase means, in one line — for the screen, not for the code.
#: The labels live here because this is where they are decided.
LABELS = {
    READING: "read and understand",
    WRITING: "produce code",
    VERIFYING: "judge what is written",
    DELIVERING: "commit",
    OTHER: "unclassified — the heuristic did not know",
}

#: Each phase's letter, and its colour. Both live HERE because they are
#: read in three places — the list's strip, the sheet's strip, and the
#: legend. Three copies would end up no longer saying the same thing, and
#: a legend lying about its own colours is worse than no legend at all.
LETTERS = {
    READING: "R", WRITING: "W", VERIFYING: "V",
    DELIVERING: "D", OTHER: "·",
}

COLOURS = {
    READING: "info",
    WRITING: "primary",
    VERIFYING: "warning",
    DELIVERING: "success",
    OTHER: "muted",
}

#: ``R`` → ``info``. The strip is stored as LETTERS — it is a string,
#: not a list of phases — so painting it needs the way back.
COLOUR_BY_LETTER = {
    letter: COLOURS[phase] for phase, letter in LETTERS.items()
}

#: The tools whose NAME is enough to decide. The others go through
#: reading their command.
BY_TOOL = {
    "Read": READING,
    "Grep": READING,
    "Glob": READING,
    "NotebookRead": READING,
    "WebFetch": READING,
    "WebSearch": READING,
    "Write": WRITING,
    "Edit": WRITING,
    "NotebookEdit": WRITING,
}

#: What PRECEDES the real verb and hides it: a positioning `cd`, an
#: encoding `export`, a path variable. Measured on the first ingest:
#: **24 % of the calls ended up "unclassified"**, almost all for this
#: reason — the command said
#: ``export PYTHONIOENCODING=utf-8; py -m pytest …`` and the heuristic
#: read the ``export``. A quarter of unclassified calls makes the strip
#: unbelievable, hence useless.
PRELUDE = re.compile(
    r"^\s*(?:"
    r"cd\s+[^&;|]+(?:&&|;)"          # cd … && …
    r"|export\s+\w+=[^;]*;"          # export VAR=… ;
    r"|\w+=(?:\"[^\"]*\"|'[^']*'|[^\s;]+)\s*(?:;|&&)?"  # VAR=… ;
    r")\s*"
)


def strip_prelude(command: str) -> str:
    """The command without what precedes it — applied to a fixed point.

    A command in this repository often stacks two (``cd`` then
    ``export``), so a single pass is not enough.
    """
    previous = None
    while previous != command:
        previous = command
        command = PRELUDE.sub("", command, count=1)
    return command


#: ⚠️ THE ORDER MATTERS: `git commit` wins over `git add`, and `pytest`
#: over a `cd` preceding it. So we test from the most specific phase to
#: the most general, and the first pattern that bites decides.
#:
#: Every pattern is anchored on a WORD (``\b``): without that, `check`
#: would bite on `checkout` and file a `git checkout` as verification.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (DELIVERING, re.compile(r"\bgit\s+(commit|push|tag|revert)\b")),
    (
        VERIFYING,
        re.compile(
            r"\bpytest\b|\bruff\s+check\b|\blint-imports\b|\bimportlinter\b"
            r"|\bmypy\b|cli\.main\s+check\b|cli\.main\s+probe\b"
            r"|\bprobe_\w+\.py\b"
        ),
    ),
    # `describe` is READING and not verification: it answers "what
    # exists", not "is this right". Filing them together would erase
    # precisely the distinction being measured.
    (READING, re.compile(r"cli\.main\s+describe\b|\bgit\s+(log|show|diff|status)\b")),
    (
        READING,
        re.compile(
            r"^\s*(cat|sed|head|tail|less|grep|rg|ls|find|wc|du|tree)\b"
            r"|\|\s*(grep|rg|head|tail|wc)\b"
        ),
    ),
    # A Python heredoc, a `>` or a `tee`: it is a file WRITE disguised
    # as a shell command. The failure mode without this line is silent —
    # all the production would go to `OTHER`.
    (WRITING, re.compile(r"<<\s*'?\w+'?\s*$|>\s*[\w./-]+\.\w+|\btee\b|\bsed\s+-i\b")),
    (DELIVERING, re.compile(r"\bgit\s+(add|mv|rm|stash)\b")),
    # ⚠️ A `py -c` is ambiguous by nature — it reads as much as it
    # writes. We decide on what it DOES: a file write shows
    # (`write_text`, `open(..., "w")`), all the rest is inspection.
    # Guessing "reading" without this distinction would file the editing
    # scripts as reading, and they are how this repository writes most of
    # its files.
    (WRITING, re.compile(r"\bwrite_text\b|\bopen\([^)]*[\"']w[\"']|\bdump\(")),
    (READING, re.compile(r"\bpy(thon)?\b\s+-c\b|\bpython\b\s+-\s*$|\bread_text\b")),
)


def phase_of(tool: str, command: str = "") -> str:
    """A call's phase — its tool, and its command if it is a shell.

    ``command`` is the COMPLETE command, not its label: the deciding verb
    often comes after a preamble, and sometimes on the second line of a
    string. The short label, for its part, serves the display and is
    computed elsewhere.
    """
    direct = BY_TOOL.get(tool)
    if direct is not None:
        return direct
    if not command:
        return OTHER
    # The WHOLE command, not its first line: the verb that counts often
    # comes after a `cd` or an `export`, and sometimes on the second line
    # of a string.
    useful = strip_prelude(" ".join(command.split()))
    for phase, pattern in PATTERNS:
        if pattern.search(useful):
            return phase
    return OTHER


def sequence(phases: list[str]) -> str:
    """The strip, compressed: repetitions reduce to one letter.

    ``[reading, reading, reading, writing]`` → ``"R W"``. What we want to
    see is not how many calls, it is how many TIMES the phase changes —
    and a 600-letter strip no longer reads.
    """
    out: list[str] = []
    for phase in phases:
        letter = LETTERS.get(phase, "·")
        if not out or out[-1] != letter:
            out.append(letter)
    return " ".join(out)


def verification_cycles(phases: list[str]) -> int:
    """How many TIMES verification was entered in this task.

    It is the measurement of the rule the user set: you code everything,
    you verify, you correct, and one last verify. **Two cycles, no
    more.** Three means starting over; ten, coding by trial and error
    using the test suite as a compiler.

    Counted on the BLOCKS and not on the calls: launching three suites in
    a row is ONE verification cycle, not three.
    """
    cycles = 0
    inside = False
    for phase in phases:
        if phase == VERIFYING and not inside:
            cycles += 1
            inside = True
        elif phase in (WRITING, READING):
            inside = False
    return cycles


#: The ceiling the user set on 2026-09-12: "you code everything, you run
#: the check, you correct, and one last one — two global checks, no more,
#: no endless back-and-forth". It lives here rather than in the screen:
#: it is a rule of the repository, not a display detail.
CYCLES_MAX = 2


def verdict(cycles: int, errors: int) -> str:
    """A task's verdict, in one word — what the list sorts on."""
    if cycles > CYCLES_MAX:
        return "back-and-forth"
    if errors:
        return "corrected"
    return "first time"


feature = Feature(
    name="phases",
    kind="logic",
    provides=[phase_of, sequence, verification_cycles, verdict,
              strip_prelude],
)
