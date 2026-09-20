"""Typed state for Bretzel applications."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bretzel.state.fields.computed import ComputedProperty as ComputedProperty
from bretzel.state.fields.computed import computed
from bretzel.state.fields.descriptor import MISSING as MISSING
from bretzel.state.fields.descriptor import Field as Field
from bretzel.state.fields.descriptor import field
from bretzel.state.fields.validator import FormError, validator
from bretzel.state.fields.validator import Validator as Validator
from bretzel.state.live_connection import LiveConnection
from bretzel.state.locking import LockTimeoutError
from bretzel.state.persistence.base import Backend as Backend
from bretzel.state.persistence.client_bridge import (
    full_field_dict as full_field_dict,
)
from bretzel.state.persistence.client_bridge import (
    instance_key as instance_key,
)
from bretzel.state.persistence.memory import MemoryBackend as MemoryBackend
from bretzel.state.persistence.redis import BretzelError as BretzelError
from bretzel.state.persistence.redis import RedisBackend as RedisBackend
from bretzel.state.registry import (
    AuthRequiredError,
    ScopeConfigError,
    StateHydrationError,
)
from bretzel.state.registry import (
    StateRegistry as StateRegistry,
)
from bretzel.state.registry import (
    current_registry as current_registry,
)
from bretzel.state.registry import (
    use_registry as use_registry,
)
from bretzel.state.scopes.client import (
    ClientBinding,
    ClientExpression,
    ClientState,
    ReactivityError,
)
from bretzel.state.scopes.client import (
    ClientPersist as ClientPersist,
)
from bretzel.state.scopes.client import (
    rendering_scope as rendering_scope,
)
from bretzel.state.scopes.server import ServerScope as ServerScope
from bretzel.state.scopes.server import ServerState
from bretzel.state.types import register_type

# ───────────────────────────────────────────────────────────────────────────
# Pre-scoped server bases (sugar)
# ───────────────────────────────────────────────────────────────────────────


class PageState(ServerState, scope="page"):
    """Server state living for one page instance.

    Persists across actions (keyed by ``page_id``, TTL 1h), reset on a
    full page reload (F5) — *not* single-request. Convenience base —
    equivalent to ``class MyState(ServerState, scope="page"): ...``
    """


class SessionState(ServerState, scope="session"):
    """Server state living for the user's session lifetime."""


class UserState(ServerState, scope="user"):
    """Server state attached to an authenticated user account.

    Resolution requires an authenticated user — instantiating one in a
    request without auth raises :class:`AuthRequiredError`.
    """


class AppState(ServerState, scope="app"):
    """Process-wide server state — one record shared by every request."""


# ───────────────────────────────────────────────────────────────────────────
# state.form_value — escape hatch for one-off form values
# ───────────────────────────────────────────────────────────────────────────


# Strings that HTML form encoding maps to a ``True`` boolean.
_TRUTHY_STRINGS = frozenset({"on", "true", "1", "yes"})


def form_value(
    name: str,
    default: Any = None,
    *,
    cast: Callable[[Any], Any] | None = None,
) -> Any:
    """Read a raw value from the current request form data."""
    registry = current_registry()
    if registry is None:
        return default

    raw = registry.form_data.get(name, MISSING)
    if raw is MISSING:
        return default

    if cast is None:
        return raw

    if cast is bool:
        if isinstance(raw, str):
            return raw.lower() in _TRUTHY_STRINGS
        return bool(raw)

    return cast(raw)


# ───────────────────────────────────────────────────────────────────────────
# Public surface
# ───────────────────────────────────────────────────────────────────────────


#: **What the user writes.** Nothing else.
#:
#: Removing a name from ``__all__`` does not un-import it: existing
#: explicit imports keep working identically. What changes is what
#: autocompletion, ``import *`` and the docs see.
__all__ = [
    # The two natures — the distinction carries a GUARANTEE, not a place.
    "ServerState",   # never sent to the browser
    "ClientState",   # lives in the browser, zero round trip
    # Pre-scoped server-side bases
    "PageState",
    "SessionState",
    "UserState",
    "AppState",
    # Declaring a field
    "field",
    "register_type",
    "computed",
    "validator",
    "FormError",     # raised by an instance validator → cross-field error
    # Escape hatch: read a form value without modelling it
    "form_value",
    # Client reactivity types — what you annotate and what you compose
    "ClientBinding",
    "ClientExpression",
    # Client state owned by the framework (the runtime writes it)
    "LiveConnection",
    # The errors a user may want to catch
    "AuthRequiredError",
    "LockTimeoutError",
    "ReactivityError",
    "ScopeConfigError",
    "StateHydrationError",
]

#: **Re-exported for the OTHER LAYERS, not for an app author.**
#:
#: A facade has two audiences and they were not distinguished: what the
#: user writes, and what neighbouring layers consume. Both lived in
#: ``__all__``, mixed together, so autocompletion offered the plumbing at
#: the same rank as ``field`` or ``Theme``.
#:
#: Every name here carries the redundant ``X as X`` alias at import: that
#: is the PEP 484 marker of an intentional re-export. The list is checked
#: by ``tests/consistency/test_public_surface_is_classified.py``: nothing
#: enters a facade without being classified on one side or the other.
_INTERNAL = [
    # Descripteurs rendus par field() / computed() / validator()
    "Field",
    "ComputedProperty",
    "Validator",
    "MISSING",
    # Persistance
    "Backend",
    "MemoryBackend",
    "RedisBackend",
    # Request-scoped registry
    "StateRegistry",
    "current_registry",
    "use_registry",
    "full_field_dict",
    "instance_key",
    # Render switch (ClientState reads return a binding)
    "rendering_scope",
    # Type aliases for the scope= / persist= kwargs
    "ServerScope",
    "ClientPersist",
    # Re-export: the canonical class lives in core, is typed on bretzel
    "BretzelError",
]
