"""Gate : ``BretzelError`` is defined exactly ONCE (core/errors.py).

History — it was defined **twice**, as two *distinct* classes :
``server/errors.py`` and ``state/persistence/redis.py``. The action
dispatcher's ``except BretzelError`` (``server/routing/actions.py``)
imported the server copy, and the FastAPI handler was registered for it
too — so a redis-raised ``BretzelError`` (e.g. a non-JSON-serialisable
field caught at ``commit()``) was a *different* class, slipped past the
``except``, and fell through to a bare 500 with the helpful diagnostic
message lost. Unified into ``core/errors.py`` 2026-07-12 (the only layer
both ``state`` and ``server`` may import under the DAG).

This gate fails at commit time the moment a second ``class BretzelError``
reappears anywhere in the package, or the server re-export drifts away
from the canonical class — so the fix stays fixed instead of silently
rotting back into two classes.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.consistency._discovery import PACKAGE_FLOOR, parsed_sources

_PKG = Path(__file__).resolve().parents[2] / "bretzel"
_CLASS_RE = re.compile(r"^class\s+BretzelError\b", re.MULTILINE)


def _definition_sites() -> list[Path]:
    return [
        s.path
        for s in parsed_sources(_PKG, floor=PACKAGE_FLOOR)
        if _CLASS_RE.search(s.text)
    ]


def test_bretzel_error_defined_once() -> None:
    sites = _definition_sites()
    rel = [str(p.relative_to(_PKG.parent)) for p in sites]
    assert len(sites) == 1, (
        f"BretzelError must be defined exactly once. Found {len(sites)} "
        f"definitions: {rel}. Two distinct classes means the server's "
        f"`except BretzelError` can't catch the other one — see "
        f"core/errors.py history."
    )
    assert sites[0].parts[-2:] == ("core", "errors.py"), (
        f"BretzelError must live in core/errors.py (importable by both "
        f"state and server under the DAG), found in {rel[0]}."
    )


def test_server_reexport_is_the_core_class() -> None:
    from bretzel.core.errors import BretzelError as CoreError
    from bretzel.server.errors import BretzelError as ServerError

    assert ServerError is CoreError, (
        "bretzel.server.errors.BretzelError must BE "
        "core.errors.BretzelError (a re-export), not a separate class."
    )
