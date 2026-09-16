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


#: **Ce que l'utilisateur écrit.** Rien d'autre.
#:
#: Retirer un nom d'``__all__`` ne le dé-importe pas : les imports
#: explicites existants continuent de marcher à l'identique. Ce qui change,
#: c'est ce que voient l'autocomplétion, le ``import *`` et la doc.
__all__ = [
    # Les deux natures — la distinction porte une GARANTIE, pas un lieu.
    "ServerState",   # jamais envoyé au navigateur
    "ClientState",   # vit dans le navigateur, zéro aller-retour
    # Bases pré-scopées côté serveur
    "PageState",
    "SessionState",
    "UserState",
    "AppState",
    # Déclarer un champ
    "field",
    "register_type",
    "computed",
    "validator",
    "FormError",     # levé par un validator d'instance → erreur cross-champ
    # Échappatoire : lire une valeur de formulaire sans la modéliser
    "form_value",
    # Types de la réactivité client — ce qu'on annote et ce qu'on compose
    "ClientBinding",
    "ClientExpression",
    # État client possédé par le framework (le runtime l'écrit)
    "LiveConnection",
    # Les erreurs qu'un utilisateur peut vouloir attraper
    "AuthRequiredError",
    "LockTimeoutError",
    "ReactivityError",
    "ScopeConfigError",
    "StateHydrationError",
]

#: **Ré-exporté pour les AUTRES COUCHES, pas pour l'auteur d'une app.**
#:
#: Une façade a deux publics et ils n'étaient pas distingués : ce que
#: l'utilisateur écrit, et ce que les couches voisines consomment. Les deux
#: vivaient dans ``__all__``, mélangés, donc l'autocomplétion proposait la
#: plomberie au même rang que ``field`` ou ``Theme``.
#:
#: Chaque nom d'ici porte l'alias redondant ``X as X`` à l'import : c'est le
#: marqueur PEP 484 du ré-export intentionnel. La liste est vérifiée par
#: ``tests/consistency/test_public_surface_is_classified.py`` : rien n'entre
#: dans une façade sans être classé d'un côté ou de l'autre.
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
    # Registre scopé à la requête
    "StateRegistry",
    "current_registry",
    "use_registry",
    "full_field_dict",
    "instance_key",
    # Bascule de rendu (les lectures de ClientState rendent un binding)
    "rendering_scope",
    # Alias de types des kwargs scope= / persist=
    "ServerScope",
    "ClientPersist",
    # Ré-export : la classe canonique vit dans core, se tape sur bretzel
    "BretzelError",
]
