"""Unit tests for ``bretzel.core.tracking``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from bretzel.core.tracking import (
    TRACKER,
    CircularDependencyError,
    DependencyTracker,
    Observer,
)


@dataclass(eq=False)
class FakeObserver:
    """Minimal observer that counts invalidations."""

    name: str = "obs"
    calls: int = 0

    def invalidate(self) -> None:
        self.calls += 1


@dataclass
class FakeSource:
    """A stand-in for a State instance."""

    name: str = "source"
    _: int = field(default=0)


# Use a fresh tracker per test to avoid leaking state between cases.
@pytest.fixture
def tracker() -> DependencyTracker:
    return DependencyTracker()


# ───────────────────────────────────────────────────────────────────────────
# Recording / notification basics
# ───────────────────────────────────────────────────────────────────────────


class TestRecording:
    def test_track_outside_observing_is_noop(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        tracker.track_access(src, "x")  # no current observer
        # Nothing recorded → notify is a no-op too.
        obs = FakeObserver()
        tracker.notify_change(src, "x")
        assert obs.calls == 0

    def test_observer_registered_and_invalidated(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs):
            tracker.track_access(src, "x")
        tracker.notify_change(src, "x")
        assert obs.calls == 1

    def test_dep_set_is_cleared_after_notify(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs):
            tracker.track_access(src, "x")
        assert tracker.has_dependents(src, "x") is True

        tracker.notify_change(src, "x")
        # Spec : observers must re-register on next evaluation.
        assert tracker.has_dependents(src, "x") is False

    def test_duplicate_track_dedupe(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs):
            for _ in range(5):
                tracker.track_access(src, "x")
        tracker.notify_change(src, "x")
        # Still exactly one invalidation despite 5 track_access calls.
        assert obs.calls == 1

    def test_two_observers_both_invalidated(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        a, b = FakeObserver("a"), FakeObserver("b")
        with tracker.observing(a):
            tracker.track_access(src, "x")
        with tracker.observing(b):
            tracker.track_access(src, "x")
        tracker.notify_change(src, "x")
        assert a.calls == 1
        assert b.calls == 1

    def test_independent_keys(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        a, b = FakeObserver("a"), FakeObserver("b")
        with tracker.observing(a):
            tracker.track_access(src, "x")
        with tracker.observing(b):
            tracker.track_access(src, "y")

        tracker.notify_change(src, "x")
        assert a.calls == 1
        assert b.calls == 0

        tracker.notify_change(src, "y")
        assert a.calls == 1
        assert b.calls == 1

    def test_notify_with_no_dependents(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        # No observer ever registered — must not raise.
        tracker.notify_change(src, "x")


# ───────────────────────────────────────────────────────────────────────────
# Nested observing()
# ───────────────────────────────────────────────────────────────────────────


class TestNesting:
    def test_inner_takes_precedence(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        outer, inner = FakeObserver("outer"), FakeObserver("inner")
        with tracker.observing(outer), tracker.observing(inner):
            tracker.track_access(src, "x")
        tracker.notify_change(src, "x")
        # Only inner was active when track_access fired.
        assert inner.calls == 1
        assert outer.calls == 0

    def test_outer_resumes_after_inner(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        outer, inner = FakeObserver("outer"), FakeObserver("inner")
        with tracker.observing(outer):
            with tracker.observing(inner):
                tracker.track_access(src, "y")
            # Back to outer scope.
            tracker.track_access(src, "x")

        tracker.notify_change(src, "y")
        tracker.notify_change(src, "x")
        assert inner.calls == 1
        assert outer.calls == 1


# ───────────────────────────────────────────────────────────────────────────
# untracked()
# ───────────────────────────────────────────────────────────────────────────


class TestUntracked:
    def test_blocks_track_access(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs), tracker.untracked():
            tracker.track_access(src, "x")
        tracker.notify_change(src, "x")
        assert obs.calls == 0

    def test_does_not_block_notify(self, tracker: DependencyTracker) -> None:
        # Spec invariant : untracked stops recording, never propagation.
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs):
            tracker.track_access(src, "x")
        with tracker.untracked():
            tracker.notify_change(src, "x")
        assert obs.calls == 1

    def test_resumes_after_block(self, tracker: DependencyTracker) -> None:
        src = FakeSource()
        obs = FakeObserver()
        with tracker.observing(obs):
            with tracker.untracked():
                tracker.track_access(src, "x")  # ignored
            tracker.track_access(src, "y")  # recorded
        tracker.notify_change(src, "x")
        tracker.notify_change(src, "y")
        assert obs.calls == 1


# ───────────────────────────────────────────────────────────────────────────
# Cycle detection
# ───────────────────────────────────────────────────────────────────────────


class TestCycleCheck:
    def test_unrelated_observer_passes(self, tracker: DependencyTracker) -> None:
        a, b = FakeObserver("a"), FakeObserver("b")
        with tracker.observing(a):
            tracker.cycle_check(b)  # b is not on the stack — no raise

    def test_self_on_stack_raises(self, tracker: DependencyTracker) -> None:
        a = FakeObserver("a")
        with tracker.observing(a), pytest.raises(CircularDependencyError):
            tracker.cycle_check(a)

    def test_ancestor_on_stack_raises(self, tracker: DependencyTracker) -> None:
        a, b = FakeObserver("a"), FakeObserver("b")
        with (
            tracker.observing(a),
            tracker.observing(b),
            pytest.raises(CircularDependencyError),
        ):
            tracker.cycle_check(a)

    def test_outside_observe_block_passes(self, tracker: DependencyTracker) -> None:
        a = FakeObserver("a")
        # Stack is empty, cycle_check is a no-op.
        tracker.cycle_check(a)


# ───────────────────────────────────────────────────────────────────────────
# Async isolation via ContextVar
# ───────────────────────────────────────────────────────────────────────────


class TestAsyncIsolation:
    def test_concurrent_tasks_isolated(self) -> None:
        tracker = DependencyTracker()
        src = FakeSource()
        a, b = FakeObserver("a"), FakeObserver("b")

        async def task_a() -> None:
            with tracker.observing(a):
                await asyncio.sleep(0)  # yield to task_b
                tracker.track_access(src, "x")

        async def task_b() -> None:
            with tracker.observing(b):
                await asyncio.sleep(0)
                tracker.track_access(src, "y")

        async def main() -> None:
            await asyncio.gather(task_a(), task_b())

        asyncio.run(main())

        tracker.notify_change(src, "x")
        tracker.notify_change(src, "y")
        # Each task saw its own observer in scope despite interleaving.
        assert a.calls == 1
        assert b.calls == 1


# ───────────────────────────────────────────────────────────────────────────
# Module-level TRACKER singleton
# ───────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_module_level_instance_exists(self) -> None:
        assert isinstance(TRACKER, DependencyTracker)

    def test_protocol_implementation(self) -> None:
        # FakeObserver structurally satisfies the Observer protocol.
        obs: Observer = FakeObserver()
        obs.invalidate()
