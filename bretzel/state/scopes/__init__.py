"""State scopes — internal aggregator.

The user-facing surface (``ServerState``, ``ClientState`` plus the
sugar aliases) is re-exported by :mod:`bretzel.state`. This package
groups the implementations only.
"""

from bretzel.state.scopes.client import (
    PERSISTS,
    ClientBinding,
    ClientExpression,
    ClientPersist,
    ClientState,
    ReactivityError,
    rendering_scope,
)
from bretzel.state.scopes.server import SCOPES, ServerScope, ServerState

__all__ = [
    "PERSISTS",
    "SCOPES",
    "ClientBinding",
    "ClientExpression",
    "ClientPersist",
    "ClientState",
    "ReactivityError",
    "ServerScope",
    "ServerState",
    "rendering_scope",
]
