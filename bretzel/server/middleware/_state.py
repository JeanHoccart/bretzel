"""Internal helpers for the pure-ASGI middleware stack.

Shared utilities the four framework middlewares (session / auth /
client_state / render_context) need to operate on raw ASGI scope
without paying the ``BaseHTTPMiddleware`` task-group cost.

- :func:`ensure_state` — get-or-upgrade ``scope["state"]`` into a
  Starlette :class:`State` (some Starlette versions and TestClient
  pre-populate it as a plain dict, which has no ``__setattr__``).
- :func:`read_header` — fetch a single header value out of
  ``scope["headers"]`` without constructing a Starlette Request.
"""

from __future__ import annotations

from starlette.datastructures import State
from starlette.types import Scope


def ensure_state(scope: Scope) -> State:
    """Get or initialise the :class:`State` object pinned on ``scope``."""
    existing = scope.get("state")
    if isinstance(existing, State):
        return existing
    new_state = State(existing) if isinstance(existing, dict) else State()
    scope["state"] = new_state
    return new_state


def read_header(scope: Scope, name: str) -> str | None:
    """Return ``scope['headers']``'s value for ``name`` or ``None``.

    ASGI normalises header names to lowercase bytes ; we match
    accordingly.
    """
    target = name.lower().encode("latin-1")
    for k, v in scope.get("headers", ()):
        if k == target:
            return v.decode("latin-1")
    return None
