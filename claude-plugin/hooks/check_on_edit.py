"""Hook: `bretzel check` on the Python files Claude writes, however it writes them.

Claude Code hands the event as JSON on stdin. Three events, one check:

- ``PostToolUse`` on Write/Edit/MultiEdit: the file the tool wrote;
- ``PostToolUse`` on Bash/PowerShell: the project's files that changed
  since the previous check (``.bretzel/check-stamp``). An agent writes
  files from the shell as often as with Write — a here-string, a heredoc —
  and a hook that only listened to Write saw almost none of them;
- ``Stop``: every file that uses Bretzel and changed during the session,
  once, before the agent hands back. Claude Code sets
  ``stop_hook_active`` when the agent is already answering this hook: the
  second time, it is let through.

Only files of the project that import Bretzel are checked, with the
project's own interpreter (`.venv`, `venv`, the active virtualenv), where
the app's Bretzel version is installed. Clean: silent. A finding: printed
on stderr with exit code 2, which Claude Code feeds back to the model, so
the mistake is fixed while the file is still open in its mind. Where no
interpreter has Bretzel, the hook stays silent: it never blocks a project
it cannot judge. Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

#: Folders that are not the project's own code — beside every dot folder
#: (``.venv``, ``.git``, ``.bretzel``), which the walk skips by its name.
SKIPPED = {"venv", "env", "__pycache__", "node_modules", "site-packages", "build", "dist"}
STAMP = Path(".bretzel") / "check-stamp"
#: Without a stamp yet, a shell command is taken to have written what
#: changed in the last minutes.
FIRST_WINDOW_S = 600
SHELLS = {"Bash", "PowerShell"}


def interpreters(project: Path) -> list[str]:
    found = []
    for folder in (".venv", "venv", "env"):
        for tail in ("bin/python", "Scripts/python.exe"):
            candidate = project / folder / tail
            if candidate.is_file():
                found.append(str(candidate))
    if virtual := os.environ.get("VIRTUAL_ENV"):
        for tail in ("bin/python", "Scripts/python.exe"):
            if (Path(virtual) / tail).is_file():
                found.append(str(Path(virtual) / tail))
    found.append(sys.executable)
    return list(dict.fromkeys(found))


def uses_bretzel(path: Path) -> bool:
    try:
        return "bretzel" in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def project_files(project: Path, newer_than: float = 0.0) -> list[Path]:
    """The project's own ``.py`` files that use Bretzel, changed after
    ``newer_than`` (a timestamp)."""
    found = []
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIPPED and not d.startswith(".")]
        for name in files:
            path = Path(root) / name
            if name.endswith(".py") and path.stat().st_mtime > newer_than and uses_bretzel(path):
                found.append(path)
    return sorted(found)


def changed_since_last_check(project: Path) -> list[Path]:
    stamp = project / STAMP
    try:
        since = stamp.stat().st_mtime
    except OSError:
        since = time.time() - FIRST_WINDOW_S
    files = project_files(project, newer_than=since)
    try:
        stamp.parent.mkdir(exist_ok=True)
        stamp.touch()
    except OSError:
        pass
    return files


def session_start(call: dict) -> float:
    """When this session began — its transcript's creation — so that
    ``Stop`` judges what the session wrote, not the whole history."""
    try:
        stat = Path(call["transcript_path"]).stat()
    except (KeyError, TypeError, OSError):
        return time.time() - FIRST_WINDOW_S
    return getattr(stat, "st_birthtime", stat.st_ctime)


def written_file(call: dict, project: Path) -> list[Path]:
    """The file a Write/Edit names — no walk: the tool says which one."""
    raw = (call.get("tool_input") or {}).get("file_path") or ""
    if not raw.endswith(".py"):
        return []
    path = Path(raw).resolve()
    try:
        path.relative_to(project)
    except ValueError:
        return []
    return [path] if uses_bretzel(path) else []


def check(project: Path, files: list[Path]) -> str:
    """The findings of ``bretzel check`` on ``files``, or ``""``."""
    for python in interpreters(project):
        try:
            done = subprocess.run(
                [python, "-m", "bretzel", "check", *map(str, files)],
                # Two interpreters at most fit in the hook's 120 s.
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=55,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if "No module named bretzel" in done.stderr:
            continue
        return done.stdout if done.returncode == 1 and "finding" in done.stdout else ""
    return ""


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")  # the report holds « → » and « … »
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or call.get("cwd") or os.getcwd()).resolve()
    event = call.get("hook_event_name", "PostToolUse")
    if event == "Stop":
        if call.get("stop_hook_active"):
            return 0
        files = project_files(project, newer_than=session_start(call))
        intro = "Before you finish: bretzel check found something in this project — fix it:"
    elif call.get("tool_name") in SHELLS:
        files = changed_since_last_check(project)
        intro = "bretzel check found something in a file this command wrote — fix it now:"
    else:
        files = written_file(call, project)
        intro = "bretzel check found something in what you just wrote — fix it now:"
    if not files:
        return 0
    report = check(project, files)
    if report:
        print(f"{intro}\n{report}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
