"""A page whose states expired says so — instead of acting on defaults.

A ``PageState`` lives an hour. A tab left open longer, then clicked,
found its states gone: the registry gave the defaults back, and the click
acted on a selection reset to zero, without a word (macro audit of
2026-10-26, finding 5). A state left at its defaults has no row, so
« never written » and « expired » read alike: each response now leaves a
WITNESS of the rows its page holds, and an action checks it first — the
route answers the ``reload`` envelope (``routing/actions.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from bretzel.state.fields.descriptor import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.server import ServerState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


class Picked(ServerState, scope="page"):
    row: str = field(default="")


class Untouched(ServerState, scope="page"):
    open: bool = field(default=False)


def _request(backend: MemoryBackend, page: str = "p1") -> StateRegistry:
    return StateRegistry(backend, session_id="sid", page_id=page)


def _respond(registry: StateRegistry) -> None:
    run(registry.commit())
    run(registry.save_page_witness())


def _written(backend: MemoryBackend) -> None:
    first = _request(backend)
    with use_registry(first):
        Picked().row = "row 12"
        assert Untouched().open is False
    _respond(first)


def test_a_live_page_is_not_expired() -> None:
    backend = MemoryBackend()
    _written(backend)
    nxt = _request(backend)
    assert not run(nxt.page_expired())
    with use_registry(nxt):
        assert Picked().row == "row 12"


def test_a_page_whose_row_expired_says_so() -> None:
    backend = MemoryBackend()
    _written(backend)
    # The hour passes: the state's row goes, its witness stays.
    run(backend.delete("page", "sid|p1:Picked:default"))
    assert run(_request(backend).page_expired()), (
        "the page's state is gone and the next click would act on its "
        "defaults, in silence")


def test_a_state_left_at_its_defaults_is_never_expired() -> None:
    """``Untouched`` was read, never written: no row, nothing to expire —
    it must not make the page look expired."""
    backend = MemoryBackend()
    first = _request(backend)
    with use_registry(first):
        assert Untouched().open is False
    _respond(first)
    assert not run(_request(backend).page_expired())


def test_a_witness_is_per_page() -> None:
    backend = MemoryBackend()
    _written(backend)
    run(backend.delete("page", "sid|p1:Picked:default"))
    assert not run(_request(backend, page="p2").page_expired())


def test_a_later_response_keeps_the_rows_it_did_not_read() -> None:
    """An action that reads none of the page's states must not drop them
    from the witness — their expiry would no longer be seen."""
    backend = MemoryBackend()
    _written(backend)
    quiet = _request(backend)
    assert not run(quiet.page_expired())
    _respond(quiet)
    run(backend.delete("page", "sid|p1:Picked:default"))
    assert run(_request(backend).page_expired())
