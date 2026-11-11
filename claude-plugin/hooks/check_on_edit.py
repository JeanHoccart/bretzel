"""PostToolUse hook: `bretzel check` on a Python file Claude just wrote.

Claude Code hands the tool call as JSON on stdin. When the file belongs to
the project and uses Bretzel, its static rules run on that file alone
(about two seconds, nothing executed). Clean: silent. A finding: printed on
stderr with exit code 2, which Claude Code feeds back to the model, so the
mistake is fixed while the file is still open in its mind.

The check runs with the project's own interpreter (`.venv`, `venv`, the
active virtualenv), where the app's Bretzel version is installed. Where no
interpreter has Bretzel, the hook stays silent: it never blocks a project
it cannot judge. Standard library only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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


def main() -> int:
    sys.stderr.reconfigure(encoding="utf-8")  # the report holds « → » and « … »
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    raw = (call.get("tool_input") or {}).get("file_path") or ""
    if not raw.endswith(".py"):
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or call.get("cwd") or os.getcwd()).resolve()
    path = Path(raw).resolve()
    try:
        path.relative_to(project)
        text = path.read_text(encoding="utf-8")
    except (ValueError, OSError, UnicodeDecodeError):
        return 0
    if "bretzel" not in text:
        return 0
    for python in interpreters(project):
        try:
            done = subprocess.run(
                [python, "-m", "bretzel", "check", str(path)],
                cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=50,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if "No module named bretzel" in done.stderr:
            continue
        if done.returncode == 1 and "finding" in done.stdout:
            print(f"bretzel check found something in what you just wrote — fix it now:\n{done.stdout}",
                  file=sys.stderr)
            return 2
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
