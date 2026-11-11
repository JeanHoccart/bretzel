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
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from starlette.datastructures import UploadFile

from bretzel.runtime import ROUTE_ACTION, WIRE_ID_SEP
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify


class HandlerResolutionError(RuntimeError):
    """Raised when an action_id cannot be resolved or its signature
    fails verification."""


class UnsealedActionError(RuntimeError):
    """A request asks to write a state without saying which fields it
    may (:func:`writable_fields`): its page is older than the server."""


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
    """The path this handler POSTs to — what a guard must let through.

    An auth guard is default-CLOSED: it blocks everything but a public
    list. And a login page's form **posts an action**, and that action is
    as blocked as the rest — the symptom is vicious: htmx follows the
    redirection transparently, ``/login``'s HTML comes back in the
    response, and **nothing happens on screen**. No error, no message, a
    dead button.

    An app should not recompose the path by hand (``ROUTE_ACTION`` + the
    wire-id separator): it is the framework that must say it ::

        PUBLIC = {"/login", action_path(login.sign_in), *app.public_paths}

    The composition goes through :func:`encode_action_id` — the same
    encoder as the route and the action attributes, without which the
    path would drift the day the wire-id changed shape.
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


def encode_args(
    handler: Callable[..., Any] | functools.partial[Any],
    fields: Iterable[str] = (),
) -> str:
    """The ``_args`` blob: a ``partial``'s bound args, and the form
    ``fields`` this action may write into a state — its control's own
    ``name`` (cf. :func:`writable_fields`).

    Returns empty string when there is neither. Raises if a bound arg is
    not JSON-serialisable — the constraint is documented upfront so
    component authors don't ship a partial with a Decimal that crashes
    mid-flight.
    """
    bound = isinstance(handler, functools.partial)
    fields = sorted(fields)
    if not bound and not fields:
        return ""
    payload: dict[str, Any] = {
        "args": list(handler.args) if bound else [],
        "kwargs": dict(handler.keywords) if bound else {},
    }
    if fields:
        payload[FIELDS_KEY] = fields
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError) as exc:
        raise HandlerResolutionError(
            f"Bound args are not JSON-serialisable : {exc}. Bretzel only "
            "accepts str/int/float/bool/None/list/dict bound values."
        ) from exc
    return base64.urlsafe_b64encode(blob.encode("utf-8")).decode("ascii")


def _decode_payload(args_blob: str) -> dict[str, Any]:
    """The ``_args`` blob as its JSON object, shape-checked."""
    if not args_blob:
        return {"args": [], "kwargs": {}}
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
    return decoded


def decode_args(args_blob: str) -> tuple[list[Any], dict[str, Any]]:
    """Decode the ``_args`` form field (POST body) back into ``(args, kwargs)``."""
    decoded = _decode_payload(args_blob)
    return list(decoded["args"]), dict(decoded["kwargs"])


# ───────────────────────────────────────────────────────────────────────────
# Writable fields — what a request may write into a state
# ───────────────────────────────────────────────────────────────────────────

#: The key of the ``_args`` blob that names the control's own field.
FIELDS_KEY = "fields"

#: The hidden input a ``ui.form`` adds: the signed list of its controls.
FIELDS_TOKEN = "_bz_fields"

# Kept apart from the action payload (``<module>::<qualname>|…``), which
# always holds ``::``.
_TOKEN_DOMAIN = "form|"


class UploadRefusedError(ValueError):
    """A file field sent more, bigger or other files than its control
    accepts (:func:`check_uploads`)."""


def fields_token(
    names: Iterable[str],
    action_key: bytes,
    uploads: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    session_id: str,
    actions: Iterable[str] = (),
) -> str:
    """The value of a form's :data:`FIELDS_TOKEN` input, signed for one
    session: the names of the controls it renders, what each of its file
    fields accepts, and the ACTIONS rendered under it — the form's own and
    its controls'. htmx sends it with the form, by its own rules — the form
    submitted, or the form around the control that fires. Bound like an
    action's signature: a token lifted from another session's form (one
    that lists ``role``) widens nothing here; and a token
    lifted from ANOTHER FORM of the same page widens nothing either
    (:func:`form_token` takes the posted action).
    """
    payload = {"names": sorted(names), "uploads": dict(uploads or {}),
               "actions": sorted(set(actions))}
    blob = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).decode("ascii")
    signed = f"{_TOKEN_DOMAIN}{session_id}|{blob}"
    return f"{blob}.{_crypto_sign(action_key, signed, hex_len=_HMAC_HEX_LEN)}"


def form_token(
    form_data: Mapping[str, Any], action_key: bytes, *, session_id: str, action_id: str
) -> dict[str, Any] | None:
    """The form token this request carries, verified for the request's
    session and for ``action_id`` — ``None`` without one, with one that
    does not verify, or with one signed for a form whose actions do not
    include this one (it counts for nothing).

    ⚠️ Without the action, a token would be a pass for the whole page: the
    token of a search form holding a ``role`` select, joined to the POST
    of ``save(form: Account)`` whose form shows only ``name``, would write
    ``role=admin``. A token is the form's word on ITS fields, for ITS
    actions.
    """
    token = form_data.get(FIELDS_TOKEN)
    if not isinstance(token, str):
        return None
    blob, _, sig = token.rpartition(".")
    if not blob or not _crypto_verify(
        action_key, f"{_TOKEN_DOMAIN}{session_id}|{blob}", sig, hex_len=_HMAC_HEX_LEN
    ):
        return None
    payload = json.loads(base64.urlsafe_b64decode(blob))
    if not isinstance(payload, dict) or action_id not in (payload.get("actions") or ()):
        return None
    return payload


def writable_fields(
    args_blob: str, token: Mapping[str, Any] | None
) -> frozenset[str] | None:
    """The state fields this request may write.

    A handler ``def save(form: Account)`` gets the state hydrated from the
    POST, and the POST is written by the client: without this, a form
    showing ``name`` could also write ``role``. What the server rendered
    says what may come back: the control's own ``name``, signed into its
    ``_args`` blob when it registered its action, and the controls of the
    form around it, signed into the form's token (:func:`form_token`).

    ``None`` when the request carries neither — a page rendered before
    either existed.
    """
    own = _decode_payload(args_blob).get(FIELDS_KEY)
    in_form = token.get("names") if token else None
    if own is None and in_form is None:
        return None
    return frozenset(map(str, own or ())) | frozenset(map(str, in_form or ()))


def check_uploads(form_data: Mapping[str, Any], token: Mapping[str, Any] | None) -> None:
    """Hold each file field of the form to what its control accepts —
    ``accept``, ``multiple``, ``max_files``, ``max_bytes`` — or raise
    :class:`UploadRefusedError`.

    The browser checks them first (``file_upload.js``); a client that
    skips the page does not. The limits ride in the form token, so a file
    is taken only into a field that token declares: dropping the token, or
    naming another field, does not dodge them. The name and the type of a
    file are the CLIENT's declarations: ``accept`` holds the request to
    what it declares, it does not sniff the bytes.
    """
    uploads = (token or {}).get("uploads") or {}
    for name, value in form_data.items():
        sent = value if isinstance(value, list) else [value]
        if name not in uploads and any(isinstance(f, UploadFile) for f in sent):
            raise UploadRefusedError(
                f"{name!r}: a file arrived for a field no form of this page "
                f"declares — files are taken through a ``ui.form``."
            )
    for name, limits in uploads.items():
        value = form_data.get(name)
        # The part a browser sends for "no file chosen" is EMPTY: no name,
        # no byte. Anything else is a file, named or not: filtering on
        # ``f.filename`` would let a part declared ``filename=""`` carry
        # any file past ``accept``, ``max_bytes`` and ``max_files`` into
        # the handler. A browser always names a file it sends: a nameless
        # one is refused.
        files = [
            f for f in (value if isinstance(value, list) else [value])
            if isinstance(f, UploadFile) and (f.filename or _size_of(f))
        ]
        for upload in files:
            if not upload.filename:
                raise UploadRefusedError(f"{name!r}: a file arrived without a name.")
        most = limits.get("max_files") or (None if limits.get("multiple") else 1)
        if most is not None and len(files) > most:
            raise UploadRefusedError(
                f"{name!r} accepts at most {most} file(s); {len(files)} were sent."
            )
        for upload in files:
            size = _size_of(upload)
            if limits.get("max_bytes") is not None and size > limits["max_bytes"]:
                raise UploadRefusedError(
                    f"{name!r}: {upload.filename!r} weighs {size} bytes, over "
                    f"the {limits['max_bytes']} the field accepts."
                )
            if not _accepted(str(limits.get("accept") or ""), upload):
                raise UploadRefusedError(
                    f"{name!r}: {upload.filename!r} ({upload.content_type}) is not "
                    f"among {limits['accept']!r}."
                )


def _size_of(upload: UploadFile) -> int:
    if upload.size is not None:
        return upload.size
    position = upload.file.tell()
    upload.file.seek(0, 2)
    size = upload.file.tell()
    upload.file.seek(position)
    return size


def _accepted(accept: str, upload: UploadFile) -> bool:
    """``accept`` read as the browser reads it: ``.ext`` on the name,
    ``type/*`` on the type's family, ``type/sub`` on the whole type."""
    tokens = [t.strip().lower() for t in accept.split(",") if t.strip()]
    if not tokens:
        return True
    name = (upload.filename or "").lower()
    kind = (upload.content_type or "").lower()
    return any(
        name.endswith(t) if t.startswith(".")
        else kind.startswith(t[:-1]) if t.endswith("/*")
        else kind == t
        for t in tokens
    )


# ───────────────────────────────────────────────────────────────────────────
# HMAC signing — protects against URL forging
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# Refetch — a zone is served to the client it was rendered for
# ───────────────────────────────────────────────────────────────────────────

_REFETCH_DOMAIN = "refetch|"


def sign_refetch(action_key: bytes, zone: str, session_id: str) -> str:
    """The signature of a zone's refetch URL (``<zone>``) for one
    session. The refetch route renders a zone outside its page, so outside
    whatever the page checks; without this, any client that could spell the
    URL — module names are public — got the zone."""
    return _crypto_sign(
        action_key, f"{_REFETCH_DOMAIN}{zone}|{session_id}", hex_len=_HMAC_HEX_LEN
    )


def verify_refetch(action_key: bytes, zone: str, session_id: str, signature: str) -> bool:
    """Constant-time check of :func:`sign_refetch`."""
    return _crypto_verify(
        action_key, f"{_REFETCH_DOMAIN}{zone}|{session_id}", signature,
        hex_len=_HMAC_HEX_LEN,
    )


def action_hmac_payload(action_id: str, args_blob: str, ts: str, session_id: str) -> str:
    """The exact byte string signed and verified for one action.

    ``sign_action`` and ``verify_action`` MUST feed identical bytes to the
    HMAC or every action 403s ; ``idempotency_key`` reuses the same
    ``action_id|args_blob|ts|session_id`` identity (prefixed with the
    user). Defining the format ONCE here removes the copy-paste that let
    those three sites drift. Guarded by
    ``tests/consistency/test_action_payload.py``.
    """
    return f"{action_id}|{args_blob}|{ts}|{session_id}"


def sign_action(
    action_key: bytes, action_id: str, args_blob: str = "", ts: str = "",
    *, session_id: str,
) -> str:
    """Compute the HMAC-SHA256 signature for one action, in one session.

    ``session_id`` is the session the control is rendered for: a signature
    lifted from a page — a pasted export link, a captured request — does
    not verify in any other session. Rotated with the session at login and
    logout, like the CSRF token; the bridge reloads on the 403.

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
    payload = action_hmac_payload(action_id, args_blob, ts, session_id)
    return _crypto_sign(action_key, payload, hex_len=_HMAC_HEX_LEN)


def verify_action(
    action_key: bytes,
    action_id: str,
    args_blob: str,
    signature: str,
    ts: str = "",
    *,
    session_id: str,
) -> bool:
    """Constant-time comparison of the supplied signature against the
    one we'd produce for ``(action_id, args_blob, ts)`` in ``session_id``
    — the session of the request, never one the request names.

    ``action_key`` is the **derived** key, not the raw ``secret_key``.
    """
    payload = action_hmac_payload(action_id, args_blob, ts, session_id)
    return _crypto_verify(action_key, payload, signature, hex_len=_HMAC_HEX_LEN)
