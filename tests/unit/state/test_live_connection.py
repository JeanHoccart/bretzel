"""Unit tests for :class:`bretzel.state.LiveConnection`.

The ClientState mechanics are covered in ``scopes/test_client.py`` — this
locks the ``LiveConnection``-specific surface : the persist mode, the default
``connected`` value, and the canonical binding path the runtime writes
(``00_index.js`` ``ensureSse``) and apps bind a live/offline badge to.
"""

from __future__ import annotations

from bretzel import LiveConnection
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.client import rendering_scope


def _with_registry():
    return use_registry(StateRegistry(MemoryBackend()))


class TestDeclaration:
    def test_is_public_from_state(self) -> None:
        import bretzel.state as state_pkg

        assert state_pkg.LiveConnection is LiveConnection

    def test_persist_is_memory(self) -> None:
        # Connection status is ephemeral — it must never leak to
        # localStorage. "memory" (sessionStorage) is the transient tier ;
        # the runtime resets it to false on every ``ensureSse``.
        assert LiveConnection.__persist__ == "memory"

    def test_default_is_disconnected(self) -> None:
        with _with_registry():
            assert LiveConnection().connected is False


class TestBinding:
    def test_connected_binding_path(self) -> None:
        # The badge binds ``visible=LiveConnection().connected`` — the path MUST
        # match the store cell the runtime writes on EventSource ``open``.
        with _with_registry(), rendering_scope():
            path = LiveConnection().connected.binding_path()
        assert path == "$bz.state.LiveConnection.default.connected"

    def test_offline_is_the_negation(self) -> None:
        # The "connecting…/offline" badge binds ``visible=~connected`` —
        # a JS ``!`` of the same canonical path (parenthesised — cf.
        # tests/consistency/test_client_expression_atomic.py).
        with _with_registry(), rendering_scope():
            expr = (~LiveConnection().connected).binding_path()
        assert expr == "(!$bz.state.LiveConnection.default.connected)"
