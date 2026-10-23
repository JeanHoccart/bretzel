"""A loop key derived from the item is the same in every process.

Ce que cette gate ferme
-----------------------

``_extract_key`` gave ``str(hash(item))`` for a ``str`` or a ``tuple``.
Python salts those hashes per process (``PYTHONHASHSEED``): the same list
got other DOM ids after a restart, and in a second worker. A partial
rendered by worker B then carried ids that the page rendered by worker A
did not have — the morph replaced instead of merging, and the client
scopes keyed by those ids were lost. Found on 2026-10-22 by rendering the
playground twice in a row (``vstack_-79869…`` then ``vstack_-21052…``).

Two sides, as rule 8 asks:

- **it bites**: the key of a ``str`` is computed in two interpreters with
  two different seeds, and must be equal;
- **it spares**: an ``int`` keeps the key it always had (its hash is
  itself), so no existing id moves for lists of integers.
"""

from __future__ import annotations

import os
import subprocess
import sys

from bretzel.render.iteration import _extract_key

#: The proof that it bites is the two-seed test itself: before the fix
#: (``str(hash(item))``) it failed, with the old code checked out
#: (verified 2026-10-22); the ``int`` test is the side it must spare.
MUTATION_PROOF = "test_a_str_key_is_the_same_in_two_processes"

_PROBE = (
    "from bretzel.render.iteration import _extract_key;"
    "print(_extract_key('inbox', None, 0), _extract_key(('a', 1), None, 0))"
)


def key_in_a_fresh_process(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    out = subprocess.run([sys.executable, "-c", _PROBE], env=env, capture_output=True,
                         text=True, check=True)
    return out.stdout.strip()


def test_a_str_key_is_the_same_in_two_processes() -> None:
    first, second = key_in_a_fresh_process("1"), key_in_a_fresh_process("2")
    assert first == second, (
        f"the same items got keys {first!r} then {second!r}: the DOM ids of a "
        "loop would change at every restart and between workers."
    )


def test_an_int_key_does_not_move() -> None:
    assert _extract_key(42, None, 0) == "42"
    assert _extract_key(True, None, 0) == "1"
