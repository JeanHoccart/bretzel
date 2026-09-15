"""``@computed`` decorator and the :class:`ComputedProperty` descriptor.

A computed is a derived value that auto-tracks its dependencies on first
evaluation and caches the result until any dependency changes. The shape
mirrors MobX / Vue computed and the spec in ``.claude/bretzel/state.md``.

Internally :

- The descriptor wraps the user's function.
- On read, a :class:`_BoundComputed` observer is paired with the host
  instance, registered with the :class:`~bretzel.core.tracking.DependencyTracker`,
  and the function is run inside an ``observing`` scope so all field
  accesses become this computed's dependencies.
- The result is cached on a per-instance ``id`` map. A weakref finalizer
  pops the entry when the host instance is garbage-collected, so the
  framework keeps no zombie state.
- When any dependency notifies a change, the bound observer is
  invalidated, which flips a dirty flag AND propagates a notification on
  ``(instance, computed_name)`` so any *downstream* observer (a renderer,
  an outer computed) re-runs too.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any

from bretzel.core.tracking import TRACKER


class ComputedProperty:
    """Descriptor backing a ``@computed`` declaration."""

    # ``__doc__`` cannot live in __slots__ — it shadows the class-level
    # docstring slot. We allow ``__dict__`` so users can still introspect
    # the wrapped function's docstring on the descriptor.
    __slots__ = ("__dict__", "_cache", "_dirty", "_finalized", "fn", "name")

    def __init__(self, fn: Callable[[Any], Any]) -> None:
        self.fn = fn
        self.name = ""
        # ``id(instance)`` → cached value / dirty flag / "we already
        # registered the GC finalizer" marker.
        self._cache: dict[int, Any] = {}
        self._dirty: dict[int, bool] = {}
        self._finalized: set[int] = set()
        self.__doc__ = getattr(fn, "__doc__", None)

    # ── Descriptor protocol ─────────────────────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any | None, owner: type | None = None) -> Any:
        if instance is None:
            return self  # class-level access yields the descriptor

        iid = id(instance)
        bound = _BoundComputed(self, instance)

        # Cycle detection BEFORE entering an observing scope, so the error
        # blames the entry point rather than appearing inside the function.
        TRACKER.cycle_check(bound)

        # Lazily install a finalizer on first access — frees cache slots
        # automatically when the host instance is collected.
        if iid not in self._finalized:
            weakref.finalize(instance, self._cleanup, iid)
            self._finalized.add(iid)

        # Recompute on first read or after invalidation.
        if self._dirty.get(iid, True):
            with TRACKER.observing(bound):
                self._cache[iid] = self.fn(instance)
            self._dirty[iid] = False

        # Outside the inner observing scope : the CALLER's current observer
        # (a render scope, an outer computed, …) becomes a dependent of
        # this computed via ``(instance, name)``.
        TRACKER.track_access(instance, self.name)
        return self._cache[iid]

    def __set__(self, instance: Any, value: Any) -> None:
        raise AttributeError(
            f"computed property {self.name!r} is read-only ; "
            "mutate the underlying state fields instead."
        )

    # ── Invalidation ────────────────────────────────────────────────────

    def invalidate(self, instance: Any) -> None:
        """Mark this computed dirty for ``instance`` and propagate.

        Called by :class:`_BoundComputed` whenever a tracked dependency
        notifies a change. We :

        1. Drop the cache and flip the dirty flag.
        2. Issue ``notify_change(instance, name)`` so anything observing
           the computed value itself re-runs.
        """
        iid = id(instance)
        self._cache.pop(iid, None)
        self._dirty[iid] = True
        TRACKER.notify_change(instance, self.name)

    def _cleanup(self, iid: int) -> None:
        """Drop all per-instance bookkeeping. Called by the weakref finalizer."""
        self._cache.pop(iid, None)
        self._dirty.pop(iid, None)
        self._finalized.discard(iid)

    def __repr__(self) -> str:
        return f"ComputedProperty(name={self.name!r}, fn={self.fn!r})"


# ───────────────────────────────────────────────────────────────────────────
# Bound observer — pairs a ComputedProperty with a specific instance.
# ───────────────────────────────────────────────────────────────────────────


class _BoundComputed:
    """An :class:`~bretzel.core.tracking.Observer` paired with a host instance.

    Identity is structural over ``(prop, instance)`` — two ``_BoundComputed``
    constructed for the same property and the same instance compare equal,
    which is what cycle detection and dep-set membership rely on.

    The instance is kept via :class:`weakref.ref` so the bound observer
    never keeps the State alive ; once the instance dies, the observer is
    inert and silently dropped.
    """

    __slots__ = ("_hash", "_instance_ref", "prop")

    def __init__(self, prop: ComputedProperty, instance: Any) -> None:
        self.prop = prop
        self._instance_ref: weakref.ReferenceType[Any] = weakref.ref(instance)
        # Pre-compute hash from the immutable identity pair so we can survive
        # the instance being collected (id reuse is not a concern : the
        # observer becomes inert at that point).
        self._hash = hash((id(prop), id(instance)))

    def invalidate(self) -> None:
        instance = self._instance_ref()
        if instance is None:
            return
        self.prop.invalidate(instance)

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _BoundComputed):
            return NotImplemented
        if self.prop is not other.prop:
            return False
        a = self._instance_ref()
        b = other._instance_ref()
        if a is None or b is None:
            return False
        return a is b

    def __repr__(self) -> str:
        instance = self._instance_ref()
        return f"_BoundComputed({self.prop.name}, instance={instance!r})"


# ───────────────────────────────────────────────────────────────────────────
# Decorator
# ───────────────────────────────────────────────────────────────────────────


def computed(fn: Callable[[Any], Any]) -> ComputedProperty:
    """Mark a method as a derived, auto-tracked, cached property.

    The decorated function ``(self) -> value`` is invoked lazily on the
    first read and cached until any field it consulted changes. Reads are
    transparent — ``cart.total`` looks like an attribute access.
    """
    return ComputedProperty(fn)
