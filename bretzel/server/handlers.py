"""Stateless action dispatch — ``module::qualname`` + HMAC signing.

Components emit their event handler ids via this scheme :
``<module>::<qualname>`` ; a short HMAC suffix ties the id to the
app's *action key* (derived from ``secret_key`` —
cf. :mod:`bretzel.server.crypto`) so an attacker can't forge URLs to
invoke arbitrary module-level functions.

Wire format on the action route :

    POST /_bretzel/action/<module>::<qualname>
        X-Bz-Sig: <hex>              # HMAC, forwarded as a header by the bridge
        body: _args=<base64-json>    # bound partial args, ride as hx-vals form-data

(Neither ``_args`` nor the signature travels in the URL query string.)
The action route handler verifies the signature, decodes the bound
args (if any) and resolves the callable through ``sys.modules``.

"""

from __future__ import annotations

import base64
import functools
import json
import sys
from collections.abc import Callable
from typing import Any

from bretzel.runtime import ROUTE_ACTION, WIRE_ID_SEP
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify


class HandlerResolutionError(RuntimeError):
    """Raised when an action_id cannot be resolved or its signature
    fails verification."""


_ACTION_ID_SEPARATOR = WIRE_ID_SEP
_HMAC_HEX_LEN = 16   # 64 bits — enough to defeat brute-force forging
                     # and short enough to keep URLs readable.


# ───────────────────────────────────────────────────────────────────────────
# Encoding — handler → addressable id
# ───────────────────────────────────────────────────────────────────────────


def encode_action_id(handler: Callable[..., Any]) -> str:
    """Return ``<module>::<qualname>`` for a module-level callable.

    Lambdas, closures and instance methods are rejected — the route
    handler resolves the callable via ``sys.modules`` + ``getattr``,
    which can only find module-level names.
    """
    if isinstance(handler, functools.partial):
        # The id describes the underlying function ; bound args go
        # into ``_args``.
        return encode_action_id(handler.func)

    if not callable(handler):
        raise TypeError(
            f"encode_action_id expects a callable, got {type(handler).__name__}."
        )

    qualname = getattr(handler, "__qualname__", "")
    module = getattr(handler, "__module__", "")
    if "<lambda>" in qualname:
        raise HandlerResolutionError(
            "Lambda handlers can't be addressed via sys.modules. "
            "Move the function to module level."
        )
    if "<locals>" in qualname:
        raise HandlerResolutionError(
            f"Closure handler {qualname!r} can't be addressed via "
            "sys.modules. Move the function to module level."
        )
    if not module or not qualname:
        raise HandlerResolutionError(
            f"Handler {handler!r} has no __module__/__qualname__."
        )
    return f"{module}{_ACTION_ID_SEPARATOR}{qualname}"


def action_path(handler: Callable[..., Any]) -> str:
    """Le chemin que POSTe ce handler — ce qu'une garde doit laisser passer.

    Une garde d'auth est en défaut-FERMÉ : elle bloque tout sauf une
    liste publique. Or le formulaire d'une page de connexion **poste une
    action**, et cette action est aussi bloquée que le reste — le
    symptôme est vicieux : htmx suit la redirection en transparence, le
    HTML de ``/login`` revient dans la réponse, et **rien ne se passe à
    l'écran**. Aucune erreur, aucun message, un bouton mort.

    ``examples/crm`` a payé ce piège le 2026-08-20 et l'a réparé en
    recomposant le chemin à la main (``ROUTE_ACTION`` + le séparateur de
    wire-id) ; ``examples/auth`` l'a repayé le 2026-08-24. Deux apps
    sur deux, donc c'est le framework qui doit le dire ::

        PUBLIC = {"/login", action_path(login.sign_in), *app.public_paths}

    La composition passe par :func:`encode_action_id` — le même encodeur
    que la route et que les attributs d'action, sans quoi le chemin
    dériverait le jour où le wire-id changerait de forme.
    """
    return f"{ROUTE_ACTION}/{encode_action_id(handler)}"


# ───────────────────────────────────────────────────────────────────────────
# Resolution — id → handler (via sys.modules)
# ───────────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=None)
def resolve_handler(action_id: str) -> Callable[..., Any]:
    """Look ``action_id`` up in ``sys.modules`` and return the callable.

    Raises :class:`HandlerResolutionError` on every failure mode :
    missing module, missing attribute, attribute that isn't callable.
    The route handler turns these into ``404`` responses (don't leak
    internals).

    Result is cached : in dev (``reload=True``) the cache dies with
    the process on every code change ; in prod modules don't mutate
    after startup so the cached callable stays correct for the
    lifetime of the worker.
    """
    if _ACTION_ID_SEPARATOR not in action_id:
        raise HandlerResolutionError(
            f"Malformed action id {action_id!r} — expected "
            f"``<module>{_ACTION_ID_SEPARATOR}<qualname>``."
        )
    module_path, qualname = action_id.split(_ACTION_ID_SEPARATOR, 1)
    module = sys.modules.get(module_path)
    if module is None:
        raise HandlerResolutionError(
            f"Module {module_path!r} is not in sys.modules. The handler's "
            "defining module must have been imported by the time the "
            "request lands — check your app's startup order."
        )
    target: Any = module
    for part in qualname.split("."):
        target = getattr(target, part, None)
        if target is None:
            raise HandlerResolutionError(
                f"Could not resolve {qualname!r} in module {module_path!r}."
            )
    if not callable(target):
        raise HandlerResolutionError(
            f"{action_id!r} resolved to {type(target).__name__}, not a callable."
        )
    return target


# ───────────────────────────────────────────────────────────────────────────
# Bound args (functools.partial) ↔ base64-JSON over the URL
# ───────────────────────────────────────────────────────────────────────────


def encode_args(handler: Callable[..., Any] | functools.partial[Any]) -> str:
    """If ``handler`` carries bound args, return their base64-JSON form.

    Returns empty string for plain callables (no bound args). Raises if
    a bound arg is not JSON-serialisable — the constraint is documented
    upfront so component authors don't ship a partial with a Decimal
    that crashes mid-flight.
    """
    if not isinstance(handler, functools.partial):
        return ""
    payload = {"args": list(handler.args), "kwargs": dict(handler.keywords)}
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError) as exc:
        raise HandlerResolutionError(
            f"Bound args are not JSON-serialisable : {exc}. Bretzel only "
            "accepts str/int/float/bool/None/list/dict bound values."
        ) from exc
    return base64.urlsafe_b64encode(blob.encode("utf-8")).decode("ascii")


def decode_args(args_blob: str) -> tuple[list[Any], dict[str, Any]]:
    """Decode the ``_args`` form field (POST body) back into ``(args, kwargs)``."""
    if not args_blob:
        return [], {}
    try:
        decoded = json.loads(base64.urlsafe_b64decode(args_blob))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HandlerResolutionError(
            f"Could not decode action args blob : {exc}."
        ) from exc
    if not isinstance(decoded, dict) or "args" not in decoded or "kwargs" not in decoded:
        raise HandlerResolutionError(
            "Action args blob has the wrong shape ; expected "
            '{"args": [...], "kwargs": {...}}.'
        )
    return list(decoded["args"]), dict(decoded["kwargs"])


# ───────────────────────────────────────────────────────────────────────────
# HMAC signing — protects against URL forging
# ───────────────────────────────────────────────────────────────────────────


def action_hmac_payload(action_id: str, args_blob: str, ts: str) -> str:
    """The exact byte string signed and verified for one action.

    ``sign_action`` and ``verify_action`` MUST feed identical bytes to the
    HMAC or every action 403s ; ``idempotency_key`` reuses the same
    ``action_id|args_blob|ts`` identity (prefixed with the user). Defining
    the format ONCE here removes the copy-paste that let those three sites
    drift. Guarded by ``tests/consistency/test_action_payload.py``.
    """
    return f"{action_id}|{args_blob}|{ts}"


def sign_action(
    action_key: bytes, action_id: str, args_blob: str = "", ts: str = ""
) -> str:
    """Compute the HMAC-SHA256 signature for ``(action_id, args_blob, ts)``.

    Truncated to :data:`_HMAC_HEX_LEN` hex chars (≈ 64 bits) — that's
    well above the brute-force-resistance threshold for a per-request
    URL parameter while keeping the URL human-debuggable.

    ``ts`` is the render timestamp (unix seconds, as a string) baked
    into ``data-bz-ts`` at render time and forwarded by the bridge as
    ``X-Bz-Ts``. Signing it lets the server (a) bound how long a captured
    request stays valid (``config.action_max_age``) and (b) use the
    signed ``(action_id, args_blob, ts)`` triple as a free idempotency
    key for ``@idempotent`` handlers — the client can't forge a fresh
    ``ts`` without the key. Empty ``ts`` reproduces the pre-v2 wire.

    ``action_key`` is the **derived** key, not the raw ``secret_key``.
    Read it from ``config._action_key`` ; the derivation happens once
    at :class:`BretzelConfig` construction.
    """
    payload = action_hmac_payload(action_id, args_blob, ts)
    return _crypto_sign(action_key, payload, hex_len=_HMAC_HEX_LEN)


def verify_action(
    action_key: bytes,
    action_id: str,
    args_blob: str,
    signature: str,
    ts: str = "",
) -> bool:
    """Constant-time comparison of the supplied signature against the
    one we'd produce for ``(action_id, args_blob, ts)``.

    ``action_key`` is the **derived** key, not the raw ``secret_key``.
    """
    payload = action_hmac_payload(action_id, args_blob, ts)
    return _crypto_verify(action_key, payload, signature, hex_len=_HMAC_HEX_LEN)
