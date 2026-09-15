"""Unit tests for ``bretzel.state.registry``."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable

import pytest

from bretzel.state.fields.descriptor import field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import (
    AuthRequiredError,
    ScopeConfigError,
    StateRegistry,
    current_registry,
    use_registry,
)
from bretzel.state.scopes.client import ClientState
from bretzel.state.scopes.server import ServerState


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


# ───────────────────────────────────────────────────────────────────────────
# Sample state classes used across the suite
# ───────────────────────────────────────────────────────────────────────────


class CartState(ServerState, scope="session"):
    items: list[int] = field(default_factory=list)
    coupon: str = field(default='')


class UserPrefs(ServerState, scope="user"):
    theme: str = field(default='light')


class FeatureFlags(ServerState, scope="app"):
    enable_x: bool = field(default=False)


class FormDraft(ServerState, scope="page"):
    body: str = field(default='')


class FilterState(ClientState, persist="local"):
    sort_by: str = field(default='date')
    is_active: bool = field(default=False)


# ───────────────────────────────────────────────────────────────────────────
# Cache primitives + contextvar binding
# ───────────────────────────────────────────────────────────────────────────


class TestContextvar:
    def test_no_active_registry(self) -> None:
        # Outside any ``use_registry`` block, current_registry() is None.
        assert current_registry() is None

    def test_use_registry_binds_and_unbinds(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend)

        with use_registry(registry):
            assert current_registry() is registry

        assert current_registry() is None


class TestCachePrimitives:
    def test_register_and_get_cached(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend)

        cart = CartState()
        registry.register(cart)
        assert registry.get_cached(CartState) is cart

    def test_get_cached_miss(self) -> None:
        registry = StateRegistry(MemoryBackend())
        assert registry.get_cached(CartState) is None

    def test_keys_isolate(self) -> None:
        registry = StateRegistry(MemoryBackend())
        a = CartState(key="a")
        b = CartState(key="b")
        registry.register(a, "a")
        registry.register(b, "b")
        assert registry.get_cached(CartState, "a") is a
        assert registry.get_cached(CartState, "b") is b


# ───────────────────────────────────────────────────────────────────────────
# Storage-key composition (per scope)
# ───────────────────────────────────────────────────────────────────────────


class TestStorageKeys:
    def test_session_scope(self) -> None:
        registry = StateRegistry(MemoryBackend(), session_id="sid_abc")
        key = registry._compose_storage_key("session", "CartState", "default")
        assert key == "sid_abc:CartState:default"

    def test_session_without_session_id_raises(self) -> None:
        registry = StateRegistry(MemoryBackend())
        with pytest.raises(ScopeConfigError, match="session id"):
            registry._compose_storage_key("session", "CartState", "default")

    def test_user_scope_hashes_id(self) -> None:
        registry = StateRegistry(MemoryBackend(), user_id="alice@example.com")
        key = registry._compose_storage_key("user", "UserPrefs", "default")
        expected_hash = hashlib.sha256(
            b"alice@example.com"
        ).hexdigest()
        assert key == f"{expected_hash}:UserPrefs:default"
        # The original id is NOT in the key — privacy by design.
        assert "alice" not in key

    def test_user_scope_without_user_id_raises_auth(self) -> None:
        registry = StateRegistry(MemoryBackend())
        with pytest.raises(AuthRequiredError):
            registry._compose_storage_key("user", "UserPrefs", "default")

    def test_app_scope(self) -> None:
        registry = StateRegistry(MemoryBackend())
        assert (
            registry._compose_storage_key("app", "FeatureFlags", "default")
            == "FeatureFlags:default"
        )


# ───────────────────────────────────────────────────────────────────────────
# Async resolve — backend roundtrip
# ───────────────────────────────────────────────────────────────────────────


class TestResolve:
    def test_resolve_session_loads_from_backend(self) -> None:
        backend = MemoryBackend()
        # Pre-seed : a session-scoped Cart with items already saved.
        run(backend.save("session", "sid:CartState:default", {"items": [1, 2, 3]}))
        registry = StateRegistry(backend, session_id="sid")

        cart = run(registry.resolve(CartState))
        assert isinstance(cart, CartState)
        assert cart.items == [1, 2, 3]
        # Hydration is not a user mutation.
        assert cart._dirty is False

    def test_resolve_session_no_prior_state_returns_defaults(self) -> None:
        registry = StateRegistry(MemoryBackend(), session_id="sid")
        cart = run(registry.resolve(CartState))
        assert cart.items == []  # default
        assert cart.coupon == ""

    def test_resolve_caches(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")
        a = run(registry.resolve(CartState))
        b = run(registry.resolve(CartState))
        assert a is b

    def test_resolve_app_scope(self) -> None:
        registry = StateRegistry(MemoryBackend())
        flags = run(registry.resolve(FeatureFlags))
        assert isinstance(flags, FeatureFlags)
        assert flags.enable_x is False

    def test_resolve_user_scope_hashed_storage(self) -> None:
        backend = MemoryBackend()
        # Pre-seed under the hashed-id storage key.
        hashed = hashlib.sha256(b"alice").hexdigest()
        run(
            backend.save(
                "user", f"{hashed}:UserPrefs:default", {"theme": "dark"}
            )
        )
        registry = StateRegistry(backend, user_id="alice")
        prefs = run(registry.resolve(UserPrefs))
        assert prefs.theme == "dark"

    def test_resolve_page_scope_uses_page_id(self) -> None:
        # Page-scope state is now keyed by ``page_id`` (the
        # ``bz-page-<uuid>`` echoed back via ``X-Bretzel-Page-ID``)
        # so mutations persist across actions on the same page.
        backend = MemoryBackend()
        registry = StateRegistry(backend, page_id="page-uuid-1")
        draft = run(registry.resolve(FormDraft))
        assert isinstance(draft, FormDraft)
        # First resolve : nothing in backend yet, still empty.
        assert backend._data == {}

    def test_resolve_page_scope_without_page_id_raises(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend)  # no page_id !
        import pytest

        from bretzel.state.registry import ScopeConfigError

        with pytest.raises(ScopeConfigError, match="page id"):
            run(registry.resolve(FormDraft))


# ───────────────────────────────────────────────────────────────────────────
# Commit — dirty server states get saved
# ───────────────────────────────────────────────────────────────────────────


class TestCommit:
    def test_dirty_state_saved(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")

        with use_registry(registry):
            cart = CartState()
            cart.coupon = "SUMMER"

        run(registry.commit())
        stored = run(backend.load("session", "sid:CartState:default"))
        assert stored == {"coupon": "SUMMER"}

    def test_clean_state_not_saved(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")

        with use_registry(registry):
            CartState()  # never mutated → not dirty

        run(registry.commit())
        assert backend._data == {}

    def test_commit_clears_dirty(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")

        with use_registry(registry):
            cart = CartState()
            cart.coupon = "X"
        run(registry.commit())
        assert cart._dirty is False

    def test_clientstate_not_committed(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")

        with use_registry(registry):
            f = FilterState()
            f.sort_by = "name"

        run(registry.commit())
        # ClientState is emitted via the response envelope, never
        # written to the server backend.
        assert backend._data == {}

    def test_page_scope_not_committed(self) -> None:
        backend = MemoryBackend()
        registry = StateRegistry(backend, session_id="sid")
        with use_registry(registry):
            d = FormDraft()
            d.body = "wip"
        run(registry.commit())
        assert backend._data == {}

    def test_session_ttl_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Verify the registry's TTL config flows into the backend write.
        # C'est ``merge`` qu'on espionne, pas ``save`` : le commit n'écrit
        # plus le document entier depuis le 2026-09-04 (cf. la mise à jour
        # perdue). Le TTL, lui, voyage pareil.
        backend = MemoryBackend()
        observed: list[int | None] = []
        original_merge = backend.merge

        async def spy_merge(
            scope: str,
            key: str,
            changes: dict[str, object],
            *,
            add: dict[str, object] | None = None,
            ttl: int | None = None,
        ) -> None:
            observed.append(ttl)
            await original_merge(scope, key, changes, add=add, ttl=ttl)

        monkeypatch.setattr(backend, "merge", spy_merge)

        registry = StateRegistry(backend, session_id="sid")
        with use_registry(registry):
            CartState().coupon = "X"
        run(registry.commit())

        # 24 hours by default for session scope.
        assert observed == [24 * 3600]


# ───────────────────────────────────────────────────────────────────────────
# Metaclass __call__ override — same instance per (cls, key)
# ───────────────────────────────────────────────────────────────────────────


class TestMetaclassCall:
    def test_same_instance_inside_registry(self) -> None:
        registry = StateRegistry(MemoryBackend(), session_id="sid")
        with use_registry(registry):
            a = CartState()
            b = CartState()
        assert a is b

    def test_different_keys_different_instances(self) -> None:
        registry = StateRegistry(MemoryBackend(), session_id="sid")
        with use_registry(registry):
            a = CartState(key="x")
            b = CartState(key="y")
        assert a is not b

    def test_outside_registry_fresh_instances(self) -> None:
        # Plain construction outside any scope is preserved for tests etc.
        a = CartState()
        b = CartState()
        assert a is not b


# ───────────────────────────────────────────────────────────────────────────
# Client-side hydration on construction
# ───────────────────────────────────────────────────────────────────────────


class TestClientHydration:
    def test_hydrate_on_construction(self) -> None:
        registry = StateRegistry(
            MemoryBackend(),
            client_payload={
                "FilterState.default": {"sort_by": "name", "is_active": True}
            },
        )
        with use_registry(registry):
            f = FilterState()
        assert f.sort_by == "name"
        assert f.is_active is True
        # Hydration is not a user mutation.
        assert f._dirty is False

    def test_no_payload_keeps_defaults(self) -> None:
        registry = StateRegistry(MemoryBackend())
        with use_registry(registry):
            f = FilterState()
        assert f.sort_by == "date"

    def test_unknown_field_in_payload_ignored(self) -> None:
        registry = StateRegistry(
            MemoryBackend(),
            client_payload={
                "FilterState.default": {"sort_by": "name", "removed": "x"}
            },
        )
        with use_registry(registry):
            f = FilterState()
        assert f.sort_by == "name"
        # ``removed`` is not a field — silently ignored, not an error.
        assert not hasattr(f, "removed") or getattr(f, "removed", None) != "x"


# V2's ``emit_client_envelope`` was deleted with the V3 migration — the
# envelope is built by ``render/pipeline.py`` via
# ``runtime.envelope.serialize_envelope`` (only ClientStates picked),
# covered by tests/unit/render/test_pipeline.py + runtime/test_envelope.py.
