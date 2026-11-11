"""``python -m bretzel`` runs the same CLI as the ``bretzel`` command:
the one form that works whatever ``PATH`` holds."""

from __future__ import annotations

import subprocess
import sys

from bretzel import __version__


def test_the_module_answers_like_the_command() -> None:
    done = subprocess.run([sys.executable, "-m", "bretzel", "--version"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert __version__ in done.stdout
