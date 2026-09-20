"""Iteration key context — the stable-key stack consumed by components.

Used in place of a bare ``for`` whenever a loop produces components that hold
client state (popovers, tabs, dropdowns, dialogs…). :func:`each` pushes a
stable key onto the render context's iteration stack ; components created
inside the loop pick this key up automatically and use it as their stable
identifier.

Without a stable key, an item inserted at position 0 would shift every
following item's positional ID by one. Idiomorph then sees them as "moved"
nodes, tears them down, and remounts them — which destroys their ``bz-data``
scope and any UI state they were holding (open menus, active tabs, focus,
in-flight animations).

"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# ───────────────────────────────────────────────────────────────────────────
# Iteration key stack — context-var, supports nesting
# ───────────────────────────────────────────────────────────────────────────


# A stack rather than a single value : nested ``each(...)`` calls compose
# (e.g. categories → items inside each category). The "effective" key
# exposed to components is the joined stack — so child IDs encode the
# outer iteration's identity too. Without that, an item inside category X
# at position 0 collides with the same-positioned item inside category Y.
_KEY_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "bretzel_each_key_stack", default=()
)


def current_iteration_key() -> str | None:
    """Return the joined iteration key (or ``None`` outside any ``each`` loop).

    Components consult this when their own ``key=`` kwarg is absent — that
    way a developer who just writes ``ui.popover(...)`` inside ``each``
    still gets stable identity for free.
    """
    stack = _KEY_STACK.get()
    if not stack:
        return None
    # ``_`` separator avoids collisions with single-segment keys that
    # happen to contain dots, slashes, etc.
    return "_".join(stack)


@contextmanager
def key_segment(segment: str) -> Iterator[None]:
    """Push an identity segment onto the stack, outside any loop.

    ``each`` pushes an ELEMENT's key; this helper pushes a CONTAINER's.
    It is the same composition, applied one notch higher, and for the
    reason this module already states: "without it, an element at
    position 0 of category X collides with the one of category Y".

    The case that produced it: two ``ui.table`` showing the same rows
    gave their cells IDENTICAL identities. A component born inside a
    cell's ``render=`` has no parent on the stack (it is built during the
    render, outside any ``with``), so its id is
    ``root_<kind>_<row key>`` — and two tables on the same data repeat
    exactly the same sequence. Measured on the playground's
    ``/datatable``: **nine elements sharing ``root_dropdown_100``**, one
    per table showing the row with id 100.

    It matters because ``bz-id`` is the key of TWO mechanisms: the one
    idiomorph pairs nodes with after a swap, and the one
    ``scope.absorb`` finds a client scope with. Nine candidates for one
    target means a menu opening instead of another and a subtree replaced
    instead of merged.
    """
    previous = _KEY_STACK.get()
    token = _KEY_STACK.set((*previous, segment))
    try:
        yield
    finally:
        _KEY_STACK.reset(token)


# ───────────────────────────────────────────────────────────────────────────
# Key extraction — the v1 cascade, preserved
# ───────────────────────────────────────────────────────────────────────────


def _extract_key(
    item: Any,
    key_arg: str | Callable[[Any], Any] | None,
    fallback_index: int,
    *,
    debug: bool = False,
) -> str:
    """Resolve a stable key for ``item``.

    Cascade :

    1. Explicit ``key_arg`` — callable applied to the item, or attribute /
       dict-key name to look up.
    2. ``item.id`` — the most common ORM convention.
    3. ``item.pk`` — Django / SQLAlchemy primary key.
    4. ``item["id"]`` if ``item`` is a mapping.
    5. ``hash(item)`` for hashable primitives (``str``, ``int``, ``tuple``,
       ``bool``).
    6. Positional fallback — the loop index. Emits a warning in debug mode
       so the developer notices and supplies an explicit key when needed.

    The returned value is always coerced to ``str`` so it can be embedded
    in DOM IDs without further escaping.
    """
    # 1. Explicit key argument
    if key_arg is not None:
        if callable(key_arg):
            return str(key_arg(item))
        if isinstance(item, dict):
            return str(item[key_arg])
        return str(getattr(item, key_arg))

    # 2-3. Conventional attributes
    for attr in ("id", "pk"):
        if hasattr(item, attr):
            return str(getattr(item, attr))

    # 4. Dict with "id" key
    if isinstance(item, dict) and "id" in item:
        return str(item["id"])

    # 5. Hashable primitive — hash gives a stable, deterministic key
    if isinstance(item, (str, int, tuple, bool)):
        return str(hash(item))

    # 6. Positional fallback — last resort. Warn so the dev catches it
    # before a bug report rolls in about disappearing menu state.
    if debug:
        warnings.warn(
            f"each(): no stable key found for item of type "
            f"{type(item).__name__}, falling back to positional "
            f"(index={fallback_index}). Pass key=... explicitly if this "
            "list can be reordered or mutated.",
            RuntimeWarning,
            stacklevel=4,  # surface in the user's loop, not deep in this helper
        )
    return str(fallback_index)
