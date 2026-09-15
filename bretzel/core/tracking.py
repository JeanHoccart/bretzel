"""Observer-pattern reactivity engine.

The trio :py:meth:`DependencyTracker.track_access`,
:py:meth:`~DependencyTracker.notify_change` and
:py:meth:`~DependencyTracker.observing` powers ``@computed`` properties,
auto re-render on state mutation, and any other "this depends on that"
relationship the framework needs.

Async-only by design : isolation between concurrent requests is provided
by :class:`~contextvars.ContextVar`, which propagates through ``await``
points but stops at thread boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol


class Observer(Protocol):
    """Anything that can be invalidated when one of its dependencies changes.

    Implementations must be hashable (used as set members) and should make
    :py:meth:`invalidate` idempotent — multiple calls before re-evaluation
    must not double-count work.
    """

    def invalidate(self) -> None: ...


class CircularDependencyError(RuntimeError):
    """Raised when an observer is detected at two levels of the eval stack."""


class DependencyTracker:
    """Coordinates dependency registration and invalidation.

    Stores a single dependency map keyed by ``(id(source), field_name)``
    and uses :class:`~contextvars.ContextVar` to scope the "currently
    recording" observer per async task.
    """

    __slots__ = ("_current", "_deps", "_stack", "_tracking_enabled")

    def __init__(self) -> None:
        self._deps: dict[tuple[int, str], set[Observer]] = {}
        self._current: ContextVar[Observer | None] = ContextVar(
            "bretzel_tracker_current", default=None
        )
        self._stack: ContextVar[tuple[Observer, ...]] = ContextVar(
            "bretzel_tracker_stack", default=()
        )
        self._tracking_enabled: ContextVar[bool] = ContextVar(
            "bretzel_tracker_enabled", default=True
        )

    # ── Recording side ───────────────────────────────────────────────────

    def track_access(self, source: object, key: str) -> None:
        """Register the active observer as dependent on ``(source, key)``.

        No-op if no observer is currently active or if tracking has been
        suspended via :py:meth:`untracked`.
        """
        if not self._tracking_enabled.get():
            return
        observer = self._current.get()
        if observer is None:
            return
        slot = (id(source), key)
        bucket = self._deps.get(slot)
        if bucket is None:
            bucket = set()
            self._deps[slot] = bucket
        bucket.add(observer)

    # ── Notification side ────────────────────────────────────────────────

    def notify_change(self, source: object, key: str) -> None:
        """Invalidate every observer that registered against ``(source, key)``.

        The dependency set is **cleared** as part of the call : invalidated
        observers are expected to re-record their dependencies on next
        evaluation. This means a single notification can never cause the
        same observer to be invalidated twice for the same key.
        """
        observers = self._deps.pop((id(source), key), None)
        if not observers:
            return
        # Snapshot to a list — invalidation callbacks may mutate the map.
        for observer in list(observers):
            observer.invalidate()

    # ── Scope management ─────────────────────────────────────────────────

    @contextmanager
    def observing(self, observer: Observer) -> Iterator[None]:
        """Bind ``observer`` as the recipient of any ``track_access`` made
        within the ``with`` block.

        Nested ``observing`` calls compose : on exit, the previous observer
        (if any) is restored. The active stack is also tracked so that
        :py:meth:`cycle_check` can detect re-entrancy.
        """
        current_token = self._current.set(observer)
        stack_token = self._stack.set((*self._stack.get(), observer))
        try:
            yield
        finally:
            self._stack.reset(stack_token)
            self._current.reset(current_token)

    @contextmanager
    def untracked(self) -> Iterator[None]:
        """Suspend dependency recording for the duration of the block.

        ``track_access`` becomes a no-op ; ``notify_change`` is **not**
        affected (it must always reach observers regardless of who is
        observing).
        """
        token = self._tracking_enabled.set(False)
        try:
            yield
        finally:
            self._tracking_enabled.reset(token)

    def cycle_check(self, observer: Observer) -> None:
        """Raise :class:`CircularDependencyError` if ``observer`` is already
        present on the active evaluation stack.

        Call this at the entry of an evaluator (e.g., the ``@computed``
        getter) before opening an :py:meth:`observing` scope, so that
        mutual recursion is detected before infinite loop.
        """
        if observer in self._stack.get():
            raise CircularDependencyError(
                f"Circular dependency detected on {observer!r} : "
                "the observer is already on the evaluation stack."
            )

    # ── Introspection (for tests / debug) ────────────────────────────────

    def has_dependents(self, source: object, key: str) -> bool:
        """True iff at least one observer is currently registered against
        ``(source, key)``."""
        bucket = self._deps.get((id(source), key))
        return bool(bucket)


# Module-level singleton. Per-task isolation is guaranteed by ContextVar.
TRACKER = DependencyTracker()
