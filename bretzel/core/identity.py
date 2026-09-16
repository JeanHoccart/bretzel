"""Stable cross-render IDs.

Components need IDs that are reproducible across renders so that idiomorph
can pair the old and new DOM nodes correctly. The :class:`IdGenerator`
hands them out in a deterministic, scope-local fashion.

Two flavours :

- **Positional** : ``next(parent, kind)`` returns ``{parent}_{kind}_{n}``
  where ``n`` is a per-(parent, kind) counter. Identity follows position.
- **Keyed** : ``next(parent, kind, key="x")`` returns ``{parent}_{kind}_x``.
  Identity follows the supplied key, surviving reordering and additions.
  Une clé identifie un EMPLACEMENT, pas un composant : deux frères du
  même genre sous la même clé sont deux composants, donc le second
  reçoit ``…_x_1``. Cf. :meth:`IdGenerator.next`.

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
    correctly across renders. First 8 hex of SHA-1 : collision risk is
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

        ⚠️ **Une clé désigne un emplacement, pas un composant.** Elle
        répond « quelle ligne / quel onglet », jamais « lequel des trois
        boutons de cette ligne » — donc elle ne peut pas suffire à elle
        seule. La branche keyed compte comme l'autre, sur un compteur qui
        lui est propre (``key`` fait partie du slot, sinon deux clés
        distinctes se décaleraient l'une l'autre), et ne suffixe qu'à
        partir du DEUXIÈME frère : le premier garde ``{parent}_{kind}_{key}``,
        donc tout ce qui marchait rend le même octet.

        Des frères de même genre sous une même clé reçoivent donc des ids
        distincts, ce qui permet à idiomorph et ``scope.absorb`` de retrouver
        sans ambiguïté le bon nœud après un swap.
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
