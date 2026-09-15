"""Unit tests for ``bretzel.state.fields.computed``."""

from __future__ import annotations

import gc

import pytest

from bretzel.core.tracking import CircularDependencyError, DependencyTracker
from bretzel.state.fields.computed import ComputedProperty, computed
from bretzel.state.fields.descriptor import Field


class _Stateful:
    """Minimal State-like host that supports field mutations."""

    def __init__(self) -> None:
        self._dirty = False


# ───────────────────────────────────────────────────────────────────────────
# Decorator + descriptor basics
# ───────────────────────────────────────────────────────────────────────────


class TestDecorator:
    def test_returns_computed_property(self) -> None:
        @computed
        def total(self: object) -> int:
            return 42

        assert isinstance(total, ComputedProperty)

    def test_set_name_captured(self) -> None:
        class C:
            @computed
            def total(self: object) -> int:
                return 0

        assert C.__dict__["total"].name == "total"

    def test_class_level_returns_descriptor(self) -> None:
        class C:
            @computed
            def total(self: object) -> int:
                return 0

        assert isinstance(C.total, ComputedProperty)


# ───────────────────────────────────────────────────────────────────────────
# Lazy compute + caching
# ───────────────────────────────────────────────────────────────────────────


class TestCompute:
    def test_first_read_evaluates(self) -> None:
        calls: list[int] = []

        class C(_Stateful):
            x = Field(default=10)

            @computed
            def doubled(self: object) -> int:
                calls.append(1)
                return self.x * 2  # type: ignore[attr-defined]

        c = C()
        assert c.doubled == 20
        assert calls == [1]

    def test_repeat_read_uses_cache(self) -> None:
        calls: list[int] = []

        class C(_Stateful):
            x = Field(default=10)

            @computed
            def doubled(self: object) -> int:
                calls.append(1)
                return self.x * 2  # type: ignore[attr-defined]

        c = C()
        c.doubled
        c.doubled
        c.doubled
        assert len(calls) == 1

    def test_invalidate_on_dep_change(self) -> None:
        calls: list[int] = []

        class C(_Stateful):
            x = Field(default=10)

            @computed
            def doubled(self: object) -> int:
                calls.append(1)
                return self.x * 2  # type: ignore[attr-defined]

        c = C()
        assert c.doubled == 20
        c.x = 5  # invalidates `doubled`
        assert c.doubled == 10
        assert len(calls) == 2

    def test_unrelated_change_does_not_invalidate(self) -> None:
        calls: list[int] = []

        class C(_Stateful):
            x = Field(default=10)
            y = Field(default=99)

            @computed
            def from_x(self: object) -> int:
                calls.append(1)
                return self.x  # type: ignore[attr-defined]

        c = C()
        c.from_x  # eval once
        c.y = 1  # not a dependency
        c.from_x
        assert len(calls) == 1


# ───────────────────────────────────────────────────────────────────────────
# Per-instance isolation
# ───────────────────────────────────────────────────────────────────────────


class TestPerInstance:
    def test_two_instances_independent_cache(self) -> None:
        class C(_Stateful):
            x = Field(default=0)

            @computed
            def doubled(self: object) -> int:
                return self.x * 2  # type: ignore[attr-defined]

        a, b = C(), C()
        a.x = 3
        b.x = 7
        assert a.doubled == 6
        assert b.doubled == 14

    def test_invalidating_one_does_not_affect_other(self) -> None:
        calls: dict[int, int] = {}

        class C(_Stateful):
            x = Field(default=0)

            @computed
            def doubled(self: object) -> int:
                calls[id(self)] = calls.get(id(self), 0) + 1
                return self.x * 2  # type: ignore[attr-defined]

        a, b = C(), C()
        a.doubled
        b.doubled
        a.x = 99  # invalidates a only
        a.doubled
        b.doubled
        assert calls[id(a)] == 2
        assert calls[id(b)] == 1


# ───────────────────────────────────────────────────────────────────────────
# Read-only — __set__ raises
# ───────────────────────────────────────────────────────────────────────────


class TestReadOnly:
    def test_set_raises(self) -> None:
        class C(_Stateful):
            @computed
            def total(self: object) -> int:
                return 0

        c = C()
        with pytest.raises(AttributeError, match="read-only"):
            c.total = 99  # type: ignore[misc]


# ───────────────────────────────────────────────────────────────────────────
# Cycle detection (mutual computed)
# ───────────────────────────────────────────────────────────────────────────


class TestCycle:
    def test_self_reference_raises(self) -> None:
        class C(_Stateful):
            @computed
            def loop(self: object) -> int:
                return self.loop  # type: ignore[attr-defined]

        c = C()
        with pytest.raises(CircularDependencyError):
            c.loop

    def test_mutual_recursion_raises(self) -> None:
        class C(_Stateful):
            @computed
            def a(self: object) -> int:
                return self.b  # type: ignore[attr-defined]

            @computed
            def b(self: object) -> int:
                return self.a  # type: ignore[attr-defined]

        c = C()
        with pytest.raises(CircularDependencyError):
            c.a


# ───────────────────────────────────────────────────────────────────────────
# Cascade — outer observer is invalidated through computed
# ───────────────────────────────────────────────────────────────────────────


class TestCascade:
    def test_outer_observer_invalidated_when_dep_changes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch TRACKER in BOTH descriptor and computed modules so they
        # share the same tracker instance. ``bretzel.state.fields.__init__``
        # re-exports the ``computed`` decorator, which shadows the
        # submodule of the same name on the package — we go through
        # ``sys.modules`` to fetch the actual modules unambiguously.
        import sys

        comp_mod = sys.modules["bretzel.state.fields.computed"]
        desc_mod = sys.modules["bretzel.state.fields.descriptor"]

        local = DependencyTracker()
        monkeypatch.setattr(comp_mod, "TRACKER", local)
        monkeypatch.setattr(desc_mod, "TRACKER", local)

        class FakeObs:
            def __init__(self) -> None:
                self.calls = 0

            def invalidate(self) -> None:
                self.calls += 1

        class C(_Stateful):
            x = Field(default=10)

            @computed
            def doubled(self: object) -> int:
                return self.x * 2  # type: ignore[attr-defined]

        c = C()
        outer = FakeObs()
        with local.observing(outer):
            _ = c.doubled  # outer becomes a dep of (c, "doubled")

        # Mutate dep → should invalidate the bound computed → which propagates
        # to the outer observer through notify_change(c, "doubled").
        c.x = 99
        assert outer.calls == 1


# ───────────────────────────────────────────────────────────────────────────
# Garbage collection — finalizer drops cache
# ───────────────────────────────────────────────────────────────────────────


class TestGc:
    def test_cache_drops_on_instance_collected(self) -> None:
        class C(_Stateful):
            x = Field(default=1)

            @computed
            def y(self: object) -> int:
                return self.x  # type: ignore[attr-defined]

        c = C()
        c.y  # populate cache
        descriptor = C.__dict__["y"]
        iid = id(c)
        assert iid in descriptor._cache

        del c
        gc.collect()
        assert iid not in descriptor._cache
        assert iid not in descriptor._dirty
