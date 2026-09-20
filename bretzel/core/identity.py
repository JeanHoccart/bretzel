"""Stable cross-render IDs.

Components need IDs that are reproducible across renders so that idiomorph
can pair the old and new DOM nodes correctly. The :class:`IdGenerator`
hands them out in a deterministic, scope-local fashion.

Two flavours:

- **Positional**: ``next(parent, kind)`` returns ``{parent}_{kind}_{n}``
  where ``n`` is a per-(parent, kind) counter. Identity follows position.
- **Keyed**: ``next(parent, kind, key="x")`` returns ``{parent}_{kind}_x``.
  Identity follows the supplied key, surviving reordering and additions.
  A key identifies a SLOT, not a component: two siblings of the same
  kind under the same key are two components, so the second one gets
  ``…_x_1``. Cf. :meth:`IdGenerator.next`.

The framework owns one generator per render scope (cf. ``RenderContext``
in the render layer). No module-level singleton — explicit lifetime.
"""

from __future__ import annotations

import hashlib


def hash_segment(s: str) -> str:
    """Stable 8-char hex digest used to compress IDs (and other stable
    wire ids, e.g. a ``@refreshable`` zone's ``bz-id``).

    The function is deterministic across runs — same input yields the
    same digest every time, so idiomorph keeps pairing elements
    correctly across renders. First 8 hex of SHA-1: collision risk is
    negligible at this scale.
    """
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


class IdGenerator:
    """Generate stable child identifiers within one render scope."""

    __slots__ = ("_counters",)

    def __init__(self) -> None:
        self._counters: dict[tuple[str, ...], int] = {}

    def next(
        self,
        parent: str,
        kind: str,
        *,
        key: str | None = None,
    ) -> str:
        """Return a fresh ID under ``parent`` of category ``kind``.

        ``key`` makes the ID stable across renders for the same logical item
        (use it for keyed lists). Without ``key``, the ID is positional and
        increments on each call to disambiguate sibling instances.

        ⚠️ **A key names a slot, not a component.** It answers "which
        row / which tab", never "which of the three buttons on that row"
        — so it cannot be enough on its own. The keyed branch counts like
        the other one, on a counter of its own (``key`` is part of the
        slot, otherwise two distinct keys would shift each other), and
        only suffixes from the SECOND sibling on: the first keeps
        ``{parent}_{kind}_{key}``, so everything that worked renders the
        same byte.

        Siblings of the same kind under the same key therefore get
        distinct ids, which lets idiomorph and ``scope.absorb`` find the
        right node unambiguously after a swap.
        """
        if key is not None:
            slot: tuple[str, ...] = (parent, kind, key)
            n = self._counters.get(slot, 0)
            self._counters[slot] = n + 1
            base = f"{parent}_{kind}_{key}"
            if n:
                base = f"{base}_{n}"
        else:
            slot = (parent, kind)
            n = self._counters.get(slot, 0)
            self._counters[slot] = n + 1
            base = f"{parent}_{kind}_{n}"

        return base

    def reset(self) -> None:
        """Drop all positional counters.

        Called between renders so that each request starts from ``_0``. Has
        no effect on keyed IDs since they don't consult the counters.
        """
        self._counters.clear()

    def fork(self) -> IdGenerator:
        """Return an independent generator with no shared counter state.

        Useful for rendering an isolated sub-tree (tests, snapshot helpers,
        out-of-context partials) without polluting the parent's counters.
        """
        return IdGenerator()
