"""A state that is only READ stays alive.

The duration of a scope (``page``: one hour, ``session``: a day) was set
again only when the request WROTE the state. A tab whose clicks only
read — open a detail, change nothing — lost its ``PageState`` an hour
after the last write, and the next click found the defaults: the
selection or the draft gone, with no word, since an absent row reads
like an empty one.

Now the end of a request pushes back the expiration of every server
state it read. These tests go through the registry, as a request does;
the backend contract itself is in
``persistence/test_both_backends_agree.py``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable

from bretzel.state.fields.descriptor import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.server import ServerState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


class Selection(ServerState, scope="session"):
    picked: str = field(default="")


def _request(backend: MemoryBackend) -> StateRegistry:
    return StateRegistry(backend, session_id="sid")


def _left(backend: MemoryBackend) -> float:
    (entry,) = backend._data.values()
    return entry.expires_at - time.time()


def test_a_read_pushes_back_the_expiry() -> None:
    backend = MemoryBackend()

    writer = _request(backend)
    with use_registry(writer):
        Selection().picked = "row 12"
    run(writer.commit())

    # The row is close to its end: an hour (here a day) without a write.
    (entry,) = backend._data.values()
    entry.expires_at = time.time() + 5

    reader = _request(backend)
    with use_registry(reader):
        assert Selection().picked == "row 12"
    run(reader.commit())

    assert _left(backend) > 5, (
        "a request that read the state left its expiration where it was: "
        "a tab that only reads loses its state at the end of the duration."
    )


def test_a_read_of_an_absent_state_creates_no_row() -> None:
    backend = MemoryBackend()

    reader = _request(backend)
    with use_registry(reader):
        assert Selection().picked == ""
    run(reader.commit())

    assert backend._data == {}, (
        "reading a state never written created its row: renewing must "
        "not create."
    )
