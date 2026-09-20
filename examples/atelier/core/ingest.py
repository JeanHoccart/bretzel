"""core/ingest — job: pull the session transcripts into the database.

A ``kind="job"`` feature: it renders nothing, answers no request, and
runs OUTSIDE a request — by hand
(``py -m examples.atelier.core.ingest``) or at app startup if the
database is empty.

What it reads
--------------
``~/.claude/projects/<project>/*.jsonl``: one JSON line per session
event. What interests us comes in three shapes:

- a ``user`` carrying a ``promptSource`` → a REQUEST, hence the start of
  a task;
- an ``assistant`` → its ``tool_use`` blocks (name, input) and its
  ``usage`` (tokens);
- a ``user`` carrying ``tool_result`` blocks → each call's verdict,
  including its ``is_error``.

⚠️ What it does NOT do, and why that is written down
------------------------------------------------------
It keeps **no content**: not the text of the answers, not the output of
the commands, not the body of the files written. Only tool names, times,
error flags and the first line of each command. The question asked is
"how does the work unfold", not "what was said" — and a database copying
516 MB of transcripts would be a second copy to keep up to date, in order
to answer worse than the original.

⚠️ Robustness: a transcript is a live file
---------------------------------------------
The CURRENT session writes into it while we read. A truncated line is
therefore normal, not a failure: we skip it and carry on. The count of
unreadable lines is returned, so it shows if it grows instead of keeping
quiet.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from bretzel import Feature
from examples.atelier.core.db import connect, init_db
from examples.atelier.core.phases import (
    READING,
    WRITING,
    phase_of,
    sequence,
    verdict,
    verification_cycles,
)
from examples.atelier.core.scope import dominant, scopes_in

#: Where Claude Code keeps the transcripts. The folder's name is the
#: project's path with the separators replaced by dashes.
TRANSCRIPTS = Path.home() / ".claude" / "projects"

#: A command's first significant line, truncated. Enough to recognise the
#: gesture, too little to copy a transcript.
COMMAND_MAX = 200

#: Same for the user's request: enough to recognise the task in a list,
#: not enough to re-read it.
REQUEST_MAX = 300

#: The METHOD gestures we want to see, recognised inside a command. They
#: are not tools among others: each answers a question asked about the
#: way of working.
#:
#: - ``surface``: did I ASK what exists before writing a ``ui.*``, or did
#:   I invent it? This very session invented ``ui.table_header`` and
#:   ``ui.table_row`` for want of having done so — two components that do
#:   not exist, and it is ``check`` that said so, not me;
#: - ``contract``: did I have the app MAP judged — hence the ``Feature()``
#:   and their ``uses=``? It is the question "is ``Feature()`` a
#:   construction asset, or cosmetics filled in to satisfy a gate". A
#:   contract never interrogated is the second.
GESTURE_SURFACE = re.compile(r"cli\.main\s+describe\b")
GESTURE_CONTRACT = re.compile(r"--deep\b")


def project_dir(repo: Path) -> Path:
    """A repository's transcript folder.

    ``C:\\Users\\x\\Desktop\\Jean\\bretzel`` →
    ``C--Users-x-Desktop-Jean-bretzel``. We reproduce the rule rather
    than guess: looking for "the most recent folder" would work today and
    would one day file another project's measurements.
    """
    slug = str(repo.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    return TRANSCRIPTS / slug


def events(path: Path) -> Iterator[dict[str, Any]]:
    """A transcript's events, the unreadable lines skipped."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A line truncated by a concurrent write. Skipping is
                # right; raising would make the current session's ingest
                # fail every time.
                continue


def first_line(text: str) -> str:
    """The first non-empty line, truncated — the gesture, not its content."""
    for raw in text.splitlines():
        cleaned = raw.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned[:COMMAND_MAX]
    return text.strip()[:COMMAND_MAX]


def command_of(tool: str, payload: Any) -> str:
    """What was launched, IN FULL — for the classification.

    A ``Bash`` carries its command, a ``Read`` its path, a ``Grep`` its
    pattern. The rest has nothing quotable and returns an empty string
    rather than a dictionary ``repr``, which does not read.

    ⚠️ Not truncated: it is :func:`phases.phase_of` that reads it, and
    the deciding verb often comes after a preamble. The displayed LABEL,
    for its part, goes through :func:`first_line` — two needs, two
    strings.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("command", "file_path", "pattern", "skill", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def target_of(tool: str, payload: Any) -> str:
    """What the call TOUCHES — for the scope, not for display.

    The same rule as :func:`scope.without_needles`, applied to the TOOL
    form of a search: a ``Grep``'s ``pattern`` is a needle, its ``path``
    is the haystack. :func:`command_of` returns the pattern — which is
    what we want to READ in the strip, and exactly what must not be
    counted as scope.

    Measured on 2026-09-12: the database's 205 ``Grep`` calls weighed
    nothing at all in the vote (their pattern only looks like a path by
    accident), whereas their ``path`` says precisely where we were
    looking.
    """
    if not isinstance(payload, dict):
        return ""
    if tool == "Grep":
        path = payload.get("path")
        return path if isinstance(path, str) else ""
    return command_of(tool, payload)


def text_of(content: Any) -> str:
    """A message's text, whether its content is a string or blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    pieces = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in pieces if p)


def is_real_prompt(event: dict[str, Any]) -> bool:
    """Is this a user REQUEST, and not a tool result?

    ⚠️ The distinction is the hinge of the whole splitting. A transcript's
    ``user`` is as much "write me this" as a ``tool_result`` returned by
    the harness. Confusing the two would cut a task at every command
    launched, and every rhythm measurement would become a measurement of
    nothing.
    """
    if event.get("type") != "user":
        return False
    content = (event.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    return bool(text_of(content).strip())


def minutes_between(started: str | None, ended: str | None) -> float:
    """The minutes between two ISO timestamps — ``0`` if one is missing."""
    if not started or not ended:
        return 0.0
    from datetime import datetime

    try:
        a = datetime.fromisoformat(started.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return round(max((b - a).total_seconds(), 0.0) / 60.0, 2)


def method(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """What a task's UNFOLDING says about the method followed.

    Four measurements, and all read in the ORDER of the calls — which is
    what makes them useful rather than decorative:

    - **the scope**: that of the WRITES, not the reads. Reading the base
      layer to write an app is normal; counting those reads would make
      every app task look like framework work, and the figure asked for
      would be wrong in both directions. The vote's unit is the CALL, not
      the mention: one call naming the same app twelve times counts for
      one vote. Without that, a ``py - <<PY`` rewriting a paragraph of
      CLAUDE.md quoting ``examples/ecole`` twelve times carried the whole
      task — measured on 2026-09-12 on the one that DELETED that app;
    - **read before writing**: was there at least one read BEFORE the
      first write? It is time 1 of the four-times rule, and its absence
      explains most of the extra cycles;
    - **the surface**: ``describe`` before the first write. After, it is
      verification — useful, but no longer the same question;
    - **the contract**: ``check --deep``, which arbitrates the app map.
    """
    first_write = next(
        (i for i, c in enumerate(calls) if c["phase"] == WRITING), None
    )
    before = calls if first_write is None else calls[:first_write]
    written = [s for c in calls if c["phase"] == WRITING for s in set(c["touches"])]
    every = [s for c in calls for s in set(c["touches"])]
    return {
        "scope": dominant(written or every),
        "read_first": int(any(c["phase"] == READING for c in before)),
        "surface": int(any(GESTURE_SURFACE.search(c["whole"]) for c in before)),
        "contract": int(any(GESTURE_CONTRACT.search(c["whole"]) for c in calls)),
    }


def ingest_file(conn: Any, path: Path) -> dict[str, int]:
    """Ingest ONE transcript. Returns what was seen, for the report."""
    session_id = path.stem
    conn.execute("DELETE FROM calls WHERE task_id IN "
                 "(SELECT id FROM tasks WHERE session_id = ?)", (session_id,))
    conn.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    # ``tool_use_id`` → the call awaiting its verdict. The result
    # arrives in a LATER message, so they cannot be paired on the fly
    # without this table.
    in_flight: dict[str, dict[str, Any]] = {}
    tokens_in = tokens_out = 0
    started = ended = None

    for event in events(path):
        at = event.get("timestamp")
        if at:
            started = started or at
            ended = at

        if is_real_prompt(event):
            current = {
                "rank": len(tasks) + 1,
                "started": at,
                "ended": at,
                "request": text_of((event.get("message") or {}).get("content"))
                .strip()[:REQUEST_MAX],
                "calls": [],
                "tokens": 0,
            }
            tasks.append(current)
            continue

        message = event.get("message") or {}

        if event.get("type") == "assistant":
            usage = message.get("usage") or {}
            tokens_in += int(usage.get("input_tokens") or 0)
            out = int(usage.get("output_tokens") or 0)
            tokens_out += out
            if current is not None:
                current["tokens"] += out
                if at:
                    current["ended"] = at
            for block in message.get("content") or []:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                    continue
                if current is None:
                    continue
                tool = block.get("name") or "?"
                whole = command_of(tool, block.get("input"))
                touches = scopes_in(target_of(tool, block.get("input")))
                call = {
                    "at": at,
                    "tool": tool,
                    "phase": phase_of(tool, whole),
                    "command": first_line(whole),
                    "error": 0,
                    "detail": "",
                    "target": dominant(touches),
                    "touches": touches,
                    "whole": whole,
                }
                current["calls"].append(call)
                identifier = block.get("id")
                if identifier:
                    in_flight[identifier] = call
            continue

        # A tool result: it carries the call's verdict.
        for block in message.get("content") or []:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            call = in_flight.pop(block.get("tool_use_id") or "", None)
            if call is None or not block.get("is_error"):
                continue
            call["error"] = 1
            call["detail"] = first_line(text_of(block.get("content")))
        if current is not None and at:
            current["ended"] = at

    total_calls = total_errors = exchanges = 0
    for task in tasks:
        # ⚠️ A turn that triggered NO tool is not a task: it is "ok",
        # "go ahead", or a question answered from memory. Keeping them
        # made 345 rows out of 1 857 at zero cycles and zero calls, all
        # of which dragged every average down without describing any
        # work. We COUNT them — how many exchanges it took is
        # information — without making them tasks.
        if not task["calls"]:
            exchanges += 1
            continue
        run = [c["phase"] for c in task["calls"]]
        errors = sum(c["error"] for c in task["calls"])
        cycles = verification_cycles(run)
        measures = method(task["calls"])
        total_calls += len(task["calls"])
        total_errors += errors
        # The WORKING time: from the first call to the last. The wall
        # time since the request included the user's absence.
        stamps = [c["at"] for c in task["calls"] if c["at"]]
        work = minutes_between(stamps[0], stamps[-1]) if stamps else 0.0
        cursor = conn.execute(
            "INSERT INTO tasks (session_id, rank, started, minutes, request, "
            "calls, errors, cycles, strip, verdict, tokens, scope, "
            "read_first, surface, contract) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, task["rank"], task["started"], work,
                task["request"], len(task["calls"]), errors, cycles,
                sequence(run), verdict(cycles, errors),
                task["tokens"], measures["scope"], measures["read_first"],
                measures["surface"], measures["contract"],
            ),
        )
        task_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO calls (task_id, rank, at, tool, phase, "
            "command, error, detail, target) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (task_id, i + 1, c["at"], c["tool"], c["phase"],
                 c["command"], c["error"], c["detail"], c["target"])
                for i, c in enumerate(task["calls"])
            ],
        )

    conn.execute(
        "INSERT INTO sessions (id, file, started, ended, minutes, tasks, "
        "exchanges, calls, errors, tokens_in, tokens_out) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, path.name, started, ended,
         minutes_between(started, ended),
         len(tasks) - exchanges, exchanges, total_calls, total_errors,
         tokens_in, tokens_out),
    )
    return {
        "tasks": len(tasks) - exchanges,
        "exchanges": exchanges,
        "calls": total_calls,
        "errors": total_errors,
    }


def ingest_all(repo: Path | None = None, *, reset: bool = True) -> dict[str, int]:
    """Ingest every transcript of the repository. Returns the total seen."""
    repo = repo or Path(__file__).resolve().parents[3]
    source = project_dir(repo)
    init_db(reset=reset)
    total = {"sessions": 0, "tasks": 0, "exchanges": 0, "calls": 0,
             "errors": 0}
    if not source.is_dir():
        return total
    with connect() as conn:
        for path in sorted(source.glob("*.jsonl")):
            seen = ingest_file(conn, path)
            total["sessions"] += 1
            for key in ("tasks", "exchanges", "calls", "errors"):
                total[key] += seen[key]
    return total


def main() -> int:
    """``py -m examples.atelier.core.ingest``."""
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = ingest_all()
    print(
        f"{total['sessions']} sessions, {total['tasks']} tasks, "
        f"{total['calls']} calls, {total['errors']} errors "
        f"({total['exchanges']} tool-less exchanges, set aside)."
    )
    return 0


feature = Feature(
    name="ingest",
    kind="job",
    uses=["db", "phases", "scope"],
    provides=[ingest_all, ingest_file, method],
)


if __name__ == "__main__":
    raise SystemExit(main())
