"""Unit tests for ``bretzel.state.persistence.memory``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from bretzel.state.persistence.base import Backend
from bretzel.state.persistence.memory import MemoryBackend


def run[T](coro: Awaitable[T]) -> T:
    """Drive an awaitable to completion in a fresh event loop.

    The project lacks a configured ``pytest-asyncio`` ; this helper keeps
    the tests readable without the plugin while still exercising the
    real async code path.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


def with_backend[T](fn: Callable[[MemoryBackend], Awaitable[T]]) -> T:
    return run(fn(MemoryBackend()))


# ───────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ───────────────────────────────────────────────────────────────────────────


class TestProtocol:
    def test_satisfies_backend_protocol(self) -> None:
        # ``runtime_checkable`` lets us verify structural conformance.
        backend: Backend = MemoryBackend()
        assert isinstance(backend, Backend)


# ───────────────────────────────────────────────────────────────────────────
# Read / write basics
# ───────────────────────────────────────────────────────────────────────────


class TestReadWrite:
    def test_load_missing_returns_none(self) -> None:
        async def go(b: MemoryBackend) -> None:
            assert await b.load("session", "x") is None

        with_backend(go)

    def test_save_then_load(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1, "y": "two"})
            assert await b.load("session", "abc") == {"x": 1, "y": "two"}

        with_backend(go)

    def test_save_overwrites(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1})
            await b.save("session", "abc", {"x": 2})
            assert await b.load("session", "abc") == {"x": 2}

        with_backend(go)

    def test_load_returns_defensive_copy(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1})
            loaded = await b.load("session", "abc")
            assert loaded is not None
            loaded["x"] = 999
            # Mutating the returned dict must not poison the store.
            again = await b.load("session", "abc")
            assert again == {"x": 1}

        with_backend(go)

    def test_save_isolates_from_caller_dict(self) -> None:
        async def go(b: MemoryBackend) -> None:
            payload = {"x": 1}
            await b.save("session", "abc", payload)
            payload["x"] = 999  # mutate after save
            assert await b.load("session", "abc") == {"x": 1}

        with_backend(go)

    def test_delete_removes_entry(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1})
            await b.delete("session", "abc")
            assert await b.load("session", "abc") is None

        with_backend(go)

    def test_delete_missing_is_noop(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.delete("session", "never_existed")

        with_backend(go)


# ───────────────────────────────────────────────────────────────────────────
# Scope namespacing
# ───────────────────────────────────────────────────────────────────────────


class TestScopeIsolation:
    def test_same_key_different_scopes(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"who": "session"})
            await b.save("user", "abc", {"who": "user"})
            assert (await b.load("session", "abc")) == {"who": "session"}
            assert (await b.load("user", "abc")) == {"who": "user"}

        with_backend(go)


# ───────────────────────────────────────────────────────────────────────────
# TTL behaviour
# ───────────────────────────────────────────────────────────────────────────


class TestTtl:
    def test_ttl_zero_expires_immediately(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel.state.persistence import memory as mem_mod

        clock = [1000.0]
        monkeypatch.setattr(mem_mod.time, "time", lambda: clock[0])

        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1}, ttl=10)
            assert await b.load("session", "abc") == {"x": 1}
            clock[0] = 1010.0  # exactly at the deadline → expired
            assert await b.load("session", "abc") is None

        with_backend(go)

    def test_ttl_in_past_drops_on_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel.state.persistence import memory as mem_mod

        clock = [1000.0]
        monkeypatch.setattr(mem_mod.time, "time", lambda: clock[0])

        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc", {"x": 1}, ttl=5)
            clock[0] = 2000.0  # way past the expiry
            assert await b.load("session", "abc") is None
            # And the entry was dropped — no zombie left in the store.
            assert "session:abc" not in b._data

        with_backend(go)

    def test_save_without_ttl_persists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel.state.persistence import memory as mem_mod

        clock = [1000.0]
        monkeypatch.setattr(mem_mod.time, "time", lambda: clock[0])

        async def go(b: MemoryBackend) -> None:
            await b.save("app", "flags", {"on": True})  # no ttl
            clock[0] = 1_000_000.0
            assert await b.load("app", "flags") == {"on": True}

        with_backend(go)


# ───────────────────────────────────────────────────────────────────────────
# scan
# ───────────────────────────────────────────────────────────────────────────


class TestScan:
    def test_scan_glob(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "a", {"v": 1})
            await b.save("session", "b", {"v": 2})
            await b.save("user", "z", {"v": 3})

            keys: list[str] = []
            async for k in b.scan("session:*"):
                keys.append(k)
            assert sorted(keys) == ["session:a", "session:b"]

        with_backend(go)

    def test_scan_skips_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel.state.persistence import memory as mem_mod

        clock = [1000.0]
        monkeypatch.setattr(mem_mod.time, "time", lambda: clock[0])

        async def go(b: MemoryBackend) -> None:
            await b.save("session", "a", {"v": 1}, ttl=10)
            await b.save("session", "b", {"v": 2})

            clock[0] = 1100.0  # a expired

            keys = [k async for k in b.scan("session:*")]
            assert keys == ["session:b"]

        with_backend(go)


# ───────────────────────────────────────────────────────────────────────────
# clear_scope
# ───────────────────────────────────────────────────────────────────────────


class TestClearScope:
    def test_full_scope_clear(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "a", {"v": 1})
            await b.save("session", "b", {"v": 2})
            await b.save("user", "z", {"v": 3})

            count = await b.clear_scope("session")
            assert count == 2
            assert await b.load("session", "a") is None
            assert await b.load("user", "z") == {"v": 3}

        with_backend(go)

    def test_empty_scope_returns_zero(self) -> None:
        async def go(b: MemoryBackend) -> None:
            assert await b.clear_scope("session") == 0

        with_backend(go)

    def test_pattern_narrows_clear(self) -> None:
        async def go(b: MemoryBackend) -> None:
            await b.save("session", "abc:CartState:default", {"v": 1})
            await b.save("session", "abc:UserState:default", {"v": 2})
            await b.save("session", "xyz:CartState:default", {"v": 3})

            count = await b.clear_scope("session", pattern="abc:*")
            assert count == 2
            # The non-matching one is preserved.
            remaining = [k async for k in b.scan("session:*")]
            assert remaining == ["session:xyz:CartState:default"]

        with_backend(go)


# ───────────────────────────────────────────────────────────────────────────
# health
# ───────────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_always_healthy(self) -> None:
        async def go(b: MemoryBackend) -> None:
            assert await b.health() is True

        with_backend(go)
