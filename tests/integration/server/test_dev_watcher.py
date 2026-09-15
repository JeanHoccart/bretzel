"""End-to-end integration : real watchfiles parent loop in
function-mode + PythonFilter, with a marker-file child that proves
respawn happened.

This is the test that validates the design hypothesis : on every
platform Bretzel supports, ``watchfiles.run_process(target=fn,
target_type='function')`` correctly kills + respawns the child when
a ``*.py`` file in the watched dir changes. If this passes on
Windows, the original ``--reload`` bug is fixed.

Marked ``slow`` (subprocess + timing) — runs in CI, opt-in for the
fast unit loop.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.slow]


# Module-level so watchfiles' spawn can re-import it in the child.
def _write_pid_marker(marker_path: str) -> None:
    """Child target : write the current PID to a marker file, then
    sleep forever. The parent test reads the marker to learn the
    child's PID across respawns."""
    Path(marker_path).write_text(str(os.getpid()))
    while True:
        time.sleep(0.5)


def _read_pid_when_ready(marker: Path, timeout: float = 5.0) -> int:
    """Poll the marker file until it contains a parseable PID."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            try:
                return int(marker.read_text())
            except ValueError:
                pass
        time.sleep(0.05)
    raise TimeoutError(f"marker file {marker} not ready within {timeout}s")


def _read_pid_when_changed(
    marker: Path, original: int, timeout: float = 10.0,
) -> int:
    """Poll the marker file until its PID differs from ``original``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            try:
                current = int(marker.read_text())
                if current != original:
                    return current
            except ValueError:
                pass
        time.sleep(0.05)
    raise TimeoutError(
        f"marker PID never changed from {original} within {timeout}s"
    )


class TestWatchfilesRespawn:
    def test_py_file_change_triggers_respawn(self, tmp_path: Path) -> None:
        marker = tmp_path / "child_pid.txt"
        trigger = tmp_path / "trigger.py"
        trigger.write_text("# initial content\n")

        # We launch the watcher in a separate subprocess so we can
        # cleanly terminate it at the end (the watchfiles loop blocks
        # forever on the calling thread).
        runner_script = tmp_path / "_runner.py"
        runner_script.write_text(
            f"""
from watchfiles import PythonFilter, run_process
from tests.integration.server.test_dev_watcher import _write_pid_marker

if __name__ == "__main__":
    run_process(
        {str(tmp_path)!r},
        target=_write_pid_marker,
        args=({str(marker)!r},),
        target_type="function",
        watch_filter=PythonFilter(),
    )
"""
        )

        proc = subprocess.Popen(
            [sys.executable, str(runner_script)],
            cwd=str(Path(__file__).resolve().parents[3]),  # repo root
        )
        try:
            # 1. First spawn writes its PID to the marker.
            first_pid = _read_pid_when_ready(marker, timeout=10.0)

            # 2. Touch the trigger ``.py`` — watchfiles + PythonFilter
            #    should pick it up and kill/respawn the child.
            time.sleep(0.5)  # give watchfiles its debounce window
            trigger.write_text("# changed content\n")

            # 3. Marker file now contains the NEW child's PID.
            second_pid = _read_pid_when_changed(
                marker, first_pid, timeout=15.0,
            )

            assert second_pid != first_pid, (
                f"watcher failed to respawn child : PID stayed {first_pid}. "
                "This is the original Windows bug — design broken."
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
