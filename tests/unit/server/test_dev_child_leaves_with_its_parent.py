"""A dev server's child leaves when its parent dies.

``watchfiles`` runs uvicorn in a spawned child; a parent killed abruptly
(a terminal closed, a ``timeout``, a preview stopped) told it nothing,
and it stayed — fourteen orphans on 2026-10-27, holding the folders of
three worktrees. :func:`bretzel.server._dev.exit_with_parent` makes the
child watch its parent and leave with it.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

PARENT = textwrap.dedent('''
    import multiprocessing, os, sys, time
    from pathlib import Path

    def child(beat):
        from bretzel.server._dev import exit_with_parent
        exit_with_parent()
        while True:
            Path(beat).write_text(f"{os.getpid()} {time.time()}")
            time.sleep(0.1)

    if __name__ == "__main__":
        ctx = multiprocessing.get_context("spawn")
        ctx.Process(target=child, args=(sys.argv[1],)).start()
        time.sleep(600)
''')


def test_the_child_stops_when_its_parent_is_killed(tmp_path: Path) -> None:
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    beat = tmp_path / "beat.txt"
    parent = subprocess.Popen([sys.executable, str(script), str(beat)])
    try:
        deadline = time.time() + 30
        while not beat.exists() and time.time() < deadline:
            time.sleep(0.2)
        assert beat.exists(), "the child never started"
    finally:
        parent.kill()             # abrupt: nothing is propagated
        parent.wait()
    time.sleep(3)                 # the child's watcher notices within a beat
    last = beat.read_text()
    time.sleep(1)
    alive = beat.read_text() != last
    if alive:                     # never leave the orphan this test is about
        subprocess.run(["taskkill", "/F", "/PID", last.split()[0]] if sys.platform == "win32"
                       else ["kill", "-9", last.split()[0]], capture_output=True)
    assert not alive, "the child is still beating: it outlived its parent"
