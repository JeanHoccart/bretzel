"""Reactivity refactor — the ``@refreshable(deps=, broadcast=, name=)``
surface (Phase 2) and, later, the deps→refresh wiring + ``refresh(x)``.

Phase 2 only locks the DECLARATION : the handle carries deps/broadcast/name
and is addressable by name. The deps→enqueue wiring is Phase 3.

Cf. ``.claude/bretzel/reactivity-refactor-plan.md``.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.render.decorators.refreshable import (
    _ZONE_BY_NAME,
    RefreshableHandle,
    broadcast_deps,
    enqueue_deps,
    refresh,
    refreshable,
    state_qualname,
)
from bretzel.state import AppState, field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry


class _S(AppState):
    items: list = field(default_factory=list)


class TestDualForm:
    def test_bare_form_defaults(self) -> None:
        @refreshable
        def zone_bare() -> None:  # noqa: D401
            pass

        assert isinstance(zone_bare, RefreshableHandle)
        assert zone_bare.deps == ()
        # ``broadcast`` porte les états sur lesquels la zone DIFFUSE
        # depuis le 2026-08-23 (un sous-ensemble de ``deps``), plus un
        # booléen. Vide = zone locale.
        assert zone_bare.broadcast == ()
        # default name = the module-qualified zone name
        assert zone_bare.name == zone_bare.zone_qualname

    def test_declarative_form_carries_metadata(self) -> None:
        @refreshable(deps=[_S], broadcast=[_S], name="zone_named")
        def zone_named() -> None:
            pass

        assert isinstance(zone_named, RefreshableHandle)
        assert zone_named.deps == (_S,)
        # ``broadcast=True`` reste le cas courant et veut dire « tous mes
        # deps » — l'appelant n'écrit jamais la liste deux fois.
        assert zone_named.broadcast == (_S,)
        assert zone_named.name == "zone_named"


class TestNameRegistry:
    def test_explicit_name_is_addressable(self) -> None:
        @refreshable(deps=[_S], name="my_addressable_zone")
        def zone_x() -> None:
            pass

        assert _ZONE_BY_NAME["my_addressable_zone"] is zone_x

    def test_default_name_is_registered(self) -> None:
        @refreshable(deps=[_S])
        def zone_y() -> None:
            pass

        assert _ZONE_BY_NAME[zone_y.zone_qualname] is zone_y


class TestDepsWiring:
    """Phase 3 : a state change (from the diff) enqueues exactly the zones
    that declared it in ``deps``."""

    def test_diff_returns_changed_classes(self) -> None:
        class _SE(AppState):
            items: list = field(default_factory=list)

        reg = StateRegistry(MemoryBackend())
        with use_registry(reg):
            s = _SE()
            s.items.append(1)  # in-place
            changed = reg.diff_and_notify()
        assert _SE in changed

    def test_enqueue_targets_only_declared_zones(self) -> None:
        class _SA(AppState):
            x: int = field(default=0)

        class _SB(AppState):
            y: int = field(default=0)

        @refreshable(deps=[_SA])
        def za() -> None:
            pass

        @refreshable(deps=[_SB])
        def zb() -> None:
            pass

        with render_isolated() as ctx:
            enqueue_deps(ctx, {_SA})
            assert za in ctx.refresh_queue
            assert zb not in ctx.refresh_queue

    def test_enqueue_dedups_a_multi_dep_zone(self) -> None:
        class _SC(AppState):
            x: int = field(default=0)

        class _SD(AppState):
            y: int = field(default=0)

        @refreshable(deps=[_SC, _SD])
        def zcd() -> None:
            pass

        with render_isolated() as ctx:
            enqueue_deps(ctx, {_SC, _SD})  # both deps changed
            assert ctx.refresh_queue.count(zcd) == 1  # enqueued once

    def test_no_changes_enqueues_nothing(self) -> None:
        class _SN(AppState):
            x: int = field(default=0)

        @refreshable(deps=[_SN])
        def zn() -> None:
            pass

        with render_isolated() as ctx:
            enqueue_deps(ctx, set())
            assert zn not in ctx.refresh_queue


class TestRefreshImperative:
    """Phase 4 : the single imperative trigger ``refresh(zone_or_name)``."""

    def test_refresh_by_handle_enqueues(self) -> None:
        @refreshable
        def zh() -> None:
            pass

        with render_isolated() as ctx:
            refresh(zh)
            assert zh in ctx.refresh_queue

    def test_refresh_by_name_enqueues(self) -> None:
        @refreshable(name="named_for_refresh")
        def zn() -> None:
            pass

        with render_isolated() as ctx:
            refresh("named_for_refresh")
            assert zn in ctx.refresh_queue

    def test_refresh_unknown_name_raises_loudly(self) -> None:
        with render_isolated():
            with pytest.raises(ValueError, match="no refreshable zone named"):
                refresh("nope_does_not_exist_zzz")

    def test_refresh_dedups_by_identity(self) -> None:
        @refreshable
        def zd() -> None:
            pass

        with render_isolated() as ctx:
            refresh(zd)
            refresh(zd)
            assert ctx.refresh_queue.count(zd) == 1

    def test_refresh_out_of_context_is_noop(self) -> None:
        @refreshable
        def zo() -> None:
            pass

        refresh(zo)  # no active context → no raise, no enqueue

    def test_refresh_is_publicly_exported(self) -> None:
        import bretzel

        assert bretzel.refresh is refresh


# ───────────────────────────────────────────────────────────────────────────
# Phase 5 — broadcast=True cross-client fan-out
# ───────────────────────────────────────────────────────────────────────────


class _FakeBroker:
    """Captures publish() calls so a test can assert the fan-out without a
    live SSE stream."""

    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, qualname: str, *, except_tab: str = "") -> None:
        # ``except_tab`` : l'onglet émetteur, que le vrai courtier
        # saute. Le double le reçoit et l'ignore — ce qu'il mesure,
        # c'est QUELS canaux sont publiés, pas à qui.
        del except_tab
        self.published.append(qualname)

    def subscribe(self, session_id: str, qualname: str) -> None:  # noqa: D401
        pass


class _FakeApp:
    def __init__(self, broker: _FakeBroker | None) -> None:
        self.sse_broker = broker


class _FakeCtx:
    def __init__(self, app: _FakeApp, session_id: str = "sess-1") -> None:
        self.app = app
        self.session_id = session_id
        self.refresh_queue: list = []


class TestBroadcastDeps:
    def test_broadcast_zone_fans_out(self) -> None:
        class _SB(AppState):
            x: int = field(default=0)

        @refreshable(deps=[_SB], broadcast=[_SB])
        def zb() -> None:
            pass

        broker = _FakeBroker()
        ctx = _FakeCtx(_FakeApp(broker), session_id="acting")
        broadcast_deps(ctx, {_SB})
        # Fans out the changed dep's wire qualname to every subscribed tab.
        assert broker.published == [state_qualname(_SB)]

    def test_local_only_dep_does_not_broadcast(self) -> None:
        class _SL(AppState):
            x: int = field(default=0)

        @refreshable(deps=[_SL])  # broadcast defaults to False
        def zl() -> None:
            pass

        broker = _FakeBroker()
        ctx = _FakeCtx(_FakeApp(broker))
        broadcast_deps(ctx, {_SL})
        assert broker.published == []

    def test_multi_dep_broadcast_lists_every_channel(self) -> None:
        class _SM1(AppState):
            x: int = field(default=0)

        class _SM2(AppState):
            y: int = field(default=0)

        @refreshable(deps=[_SM1, _SM2], broadcast=[_SM1, _SM2])
        def zm() -> None:
            pass

        assert set(zm._broadcast_qualnames()) == {
            state_qualname(_SM1),
            state_qualname(_SM2),
        }
        # A change to ONE dep fans out only that dep's channel.
        broker = _FakeBroker()
        ctx = _FakeCtx(_FakeApp(broker))
        broadcast_deps(ctx, {_SM2})
        assert broker.published == [state_qualname(_SM2)]

    def test_no_broker_is_a_noop(self) -> None:
        class _SNB(AppState):
            x: int = field(default=0)

        @refreshable(deps=[_SNB], broadcast=[_SNB])
        def znb() -> None:
            pass

        ctx = _FakeCtx(_FakeApp(None))
        broadcast_deps(ctx, {_SNB})  # must not raise

    def test_non_broadcast_handle_has_empty_channels(self) -> None:
        @refreshable
        def bare() -> None:
            pass

        assert bare._broadcast_qualnames() == []
