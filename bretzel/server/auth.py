"""Authentication helpers for Bretzel applications."""

from __future__ import annotations

import contextlib
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

from bretzel.render.context import current_context
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify

# The two identity DECLARATIONS, re-exported here so the whole subject
# fits in one import (``from bretzel import auth``). They live in
# ``decorators/identity.py`` because they share no plumbing with the
# cookie — only the domain.
from bretzel.server.decorators.identity import door, source

if TYPE_CHECKING:
    from starlette.types import Scope

#: **What the user writes** — what this docstring announces.
#:
#: The four VERBS act immediately; the two NOUNS declare, and nothing
#: happens before ``app.include(...)``. The word's shape says which of
#: the two you are reading — cf. the docstring of
#: :mod:`bretzel.server.decorators.identity`.
__all__ = [
    "login",
    "logout",
    "user_id",
    "is_authenticated",
    "source",
    "door",
]

#: **Re-exported for the other layers, not for an app author.**
#: ``middleware/auth.py`` verifies the cookie, ``middleware/session.py``
#: parses it, ``config`` decides its ``Secure`` attribute.
_INTERNAL = [
    "COOKIE_AUTH",
    "COOKIE_SESSION",
    "verify_auth_cookie",
    # The identity chain, played on a raw request. ``AuthMiddleware``
    # calls it on every request and ``user_id(request)`` is its public
    # door — so an app never has to name it.
    "resolve_identity",
    # The request → instance climb, shared with ``oauth.py``.
    "app_of",
    "parse_cookies_from_scope",
    "resolve_cookie_secure",
    "request_scheme",
    # ``AuthUser`` is what ``middleware/auth.py`` sets on
    # ``request.state.user``. An app neither builds nor reads it: it
    # reads ``auth.user_id()`` and joins on ITS user table.
    "AuthUser",
    # Imported from ``render``, used by the four public functions. It
    # appears here by plain module visibility — not a re-export.
    "current_context",
]

# ── Cookie names ───────────────────────────────────────────────────────────

COOKIE_AUTH = "Bretzel_auth"
COOKIE_SESSION = "Bretzel_session"


def resolve_cookie_secure(scheme: str | None, override: bool | None) -> bool:
    """Should the ``Secure`` attribute be set on the cookies?

    It is a question of **transport**, not of environment: a ``Secure``
    cookie is simply not sent back by the browser on an ``http://``
    origin. So it is derived from the request's scheme.

    This replaces a ``secure=not debug`` that tied cookie security to the
    application's mode. A lived, reproduced consequence: an internal tool
    in ``mode="prod"`` behind a LAN without TLS set ``Secure`` cookies the
    browser never sent back — session and auth dead, with no error and no
    log, the only workaround being to go back to ``mode="dev"``, which
    exposed stack traces along the way. The trap was invisible locally:
    browsers treat ``localhost`` and ``127.0.0.1`` as trusted origins and
    accept ``Secure`` cookies there.

    ``override`` (``config.secure_cookies``) short-circuits the
    derivation. It is necessary behind a proxy terminating TLS: uvicorn
    only rewrites ``scope["scheme"]`` from ``X-Forwarded-Proto`` when it
    was started with ``proxy_headers=True``. Without that the application
    sees ``http`` and would underestimate.

    Unknown scheme (synthetic render context, tests) → ``False``: only a
    positive ``https`` justifies hardening, and being wrong the other way
    would break the session instead of protecting it.
    """
    if override is not None:
        return override
    return (scheme or "").lower() == "https"


def request_scheme(request: Any) -> str:
    """A request's scheme, tolerating duck-typed objects.

    ``RenderContext.request`` is typed ``Any`` — the render base layer
    does not know Starlette — and is a plain sentinel in test contexts.
    """
    url = getattr(request, "url", None)
    scheme = getattr(url, "scheme", None) if url is not None else None
    if scheme is None:
        scheme = getattr(request, "scheme", None)
    return str(scheme or "")


def _ctx_cookie_secure(ctx: Any) -> bool:
    """``Secure`` for the cookies set from a render context."""
    config = getattr(ctx.app, "config", None)
    override = getattr(config, "secure_cookies", None) if config else None
    return resolve_cookie_secure(request_scheme(ctx.request), override)


def parse_cookies_from_scope(scope: Scope) -> dict[str, str]:
    """Parse the ``Cookie`` header on an ASGI scope into a name→value dict.

    Called once per request by the session middleware, which stashes
    the result on ``request.state.cookies`` so downstream middlewares
    (auth) read by lookup instead of re-parsing.
    """
    for k, v in scope.get("headers", ()):
        if k == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(v.decode("latin-1"))
            except Exception:
                return {}
            return {name: morsel.value for name, morsel in jar.items()}
    return {}


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Minimal auth identity — the framework only knows the id.

    Apps that need profile / role / email join from their own user
    table using ``auth.user_id()`` as the join key.
    """

    id: str
    is_authenticated: bool = True


# ───────────────────────────────────────────────────────────────────────────
# Login / logout
# ───────────────────────────────────────────────────────────────────────────


def login(user_id: str) -> None:
    """Open a session for ``user_id`` — the proof already happened.

    This function verifies **nothing**: the password, the OAuth code or
    the SSO assertion were judged before, by the app or by a door. What
    it does is transport — setting down what it takes to recognise this
    identity on the next request.

    Side-effects:

    1. Rotate ``Bretzel_session`` (anti-fixation — a fresh session id
       prevents pre-login session-fixation attacks).
    2. Set ``Bretzel_auth`` cookie (HMAC-signed) carrying ``user_id``
       + expiry timestamp.
    3. Update ``request.state.user`` so the rest of the request
       already sees the authenticated identity.

    The string requirement on ``user_id`` is intentional: whatever
    primary key the app uses (UUID, integer, email…) gets stringified
    upstream so we have one shape to sign and ship around.
    """
    if not isinstance(user_id, str) or not user_id:
        raise TypeError("user_id must be a non-empty string.")

    ctx = current_context()
    auth_key = _auth_key(ctx)
    max_age_days = _session_max_age_days(ctx)
    expires_at = int(time.time()) + max_age_days * 86400

    payload = f"{user_id}:{expires_at}"
    signature = _crypto_sign(auth_key, payload)
    cookie_value = f"{payload}.{signature}"

    secure = _ctx_cookie_secure(ctx)
    ctx.set_cookie(
        COOKIE_AUTH,
        cookie_value,
        max_age=expires_at - int(time.time()),
        httponly=True,
        samesite="lax",
        secure=secure,
    )

    # Anti-fixation : rotate session id at every privilege change.
    ctx.session_id = secrets.token_hex(16)
    ctx.set_cookie(
        COOKIE_SESSION,
        ctx.session_id,
        max_age=max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
    )

    # Make the new identity available immediately for the remainder
    # of this request.
    ctx.user_id = user_id
    _forget_identity(ctx)
    _attach_user(ctx, AuthUser(id=user_id))


def logout() -> None:
    """Clear the auth cookie + rotate the session id.

    Idempotent — safe to call when the session is already anonymous.
    """
    ctx = current_context()
    ctx.delete_cookie(COOKIE_AUTH)
    # Rotate session so anything tied to the previous one (e.g.,
    # cart contents, in-flight forms) starts fresh on the next page.
    ctx.session_id = secrets.token_hex(16)
    secure = _ctx_cookie_secure(ctx)
    ctx.set_cookie(
        COOKIE_SESSION,
        ctx.session_id,
        max_age=_session_max_age_days(ctx) * 86400,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    ctx.user_id = None
    _forget_identity(ctx)
    _attach_user(ctx, None)


# ───────────────────────────────────────────────────────────────────────────
# Read API
# ───────────────────────────────────────────────────────────────────────────


def user_id(request: Any = None) -> str | None:
    """Return the authenticated user id, or ``None`` for an anonymous request."""
    if request is not None:
        return resolve_identity(request)
    return current_context().user_id


def is_authenticated() -> bool:
    """Convenience boolean wrapper around :func:`user_id`."""
    return user_id() is not None


# ───────────────────────────────────────────────────────────────────────────
# Cookie verification (used by ``server/middleware/auth.py``)
# ───────────────────────────────────────────────────────────────────────────


def verify_auth_cookie(cookie_value: str, auth_key: bytes) -> str | None:
    """Validate a ``Bretzel_auth`` cookie and return the user id.

    Returns ``None`` for : missing cookie, malformed payload, expired
    timestamp, or signature mismatch. Constant-time signature compare
    via :func:`hmac.compare_digest`.

    ``auth_key`` is the **derived** key (``config._auth_key``), not the
    raw ``secret_key``.
    """
    if not cookie_value or "." not in cookie_value:
        return None
    try:
        payload, supplied_sig = cookie_value.rsplit(".", 1)
        user_id, expires_at_str = payload.split(":", 1)
        expires_at = int(expires_at_str)
    except (ValueError, IndexError):
        return None

    if not _crypto_verify(auth_key, payload, supplied_sig):
        return None

    if int(time.time()) >= expires_at:
        return None

    return user_id


def resolve_identity(request: Any, bretzel: Any = None) -> str | None:
    """The identity chain, played on a raw request.

    The four other identity reads do not answer in this place, and that
    is structural: a user middleware is the OUTERMOST
    (``lifecycle.py``: "user middlewares last so they wrap everything
    above"), so on the inbound it runs BEFORE the framework's.
    :func:`user_id` without an argument reads the render context, which
    is only set during the render; ``request.state.user`` is written by
    ``AuthMiddleware``, more inner than you. All that is left is the
    request itself.

    Verifying it requires the **derived** key — not the raw
    ``secret_key``. This function fetches the derived key from the
    application itself so the user middleware never touches a sensitive
    private attribute.

    Returns ``None`` for: no cookie, malformed cookie, expired, bad
    signature, no declared source recognising the request, or app not
    found. **One single return for every refusal**, because a guard
    middleware has only one decision to make — let through or redirect —
    and distinguishing the causes here would invite saying too much to an
    anonymous visitor ::

        from bretzel import auth
        from bretzel.server import action_path, redirect_response

        # ``action_path`` is not decorative: the sign-in form POSTs an
        # action, which a default-closed guard blocks like the rest. The
        # symptom looks like nothing — htmx follows the redirect
        # transparently and the button seems dead.
        PUBLIC = {"/login", action_path(sign_in), *app.public_paths}

        @app.middleware
        async def require_login(request, call_next):
            if request.url.path in PUBLIC or auth.user_id(request):
                return await call_next(request)
            return redirect_response(request, "/login")

    It returns the **identifier**, not a boolean: a guard that only wants
    to know "signed in?" tests the value's truth, while a guard that logs
    or authorises by role needs the name. A boolean would have forced the
    second to do the read again.

    **Once per request.** The result is kept on the ``scope``, because
    the chain is played TWICE on any protected request: the app's guard
    (the outermost middleware) asks ``auth.user_id(request)``, then
    ``AuthMiddleware``, more inner, asks the same thing again without
    being able to see the first answer. That is the recipe the
    documentation prescribes, so it is not a misuse — but without a memo,
    **the app's ``@auth.source`` function runs twice**, although it may
    verify a JWT or query a remote source.

    ``auth.login`` and ``auth.logout`` clear the memo — they change the
    identity in the middle of the request.

    **The order is the cookie first, then the ``@auth.source`` sources,
    in writing order.** The cookie leads because it is what carries
    browser sessions — by far the largest population — and because it is
    the only one the framework signed itself. An exception raised by a
    source **surfaces**: an identity read that breaks is an incident, not
    an anonymous visitor, and swallowing it would do exactly what this
    repository spent an audit removing (eleven sites catching a
    construction silently).
    """
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict) and _MEMO in scope:
        return scope[_MEMO]

    if bretzel is None:
        # Internal callers pass it explicitly — they already have it,
        # and depending on how we are mounted would be fragile on that
        # path.
        bretzel = app_of(request)
    found = _from_signed_cookie(request, bretzel)
    if not found:
        for source in getattr(bretzel, "identity_sources", ()):
            found = source(request)
            if found:
                break
        else:
            found = None

    if isinstance(scope, dict):
        scope[_MEMO] = found
    return found


#: The key a request keeps the already-resolved identity under. In the
#: ASGI ``scope`` and not on ``request.state``: the two layers that read
#: it each build their own ``Request``, but share the scope — it is the
#: only place linking them.
_MEMO = "_bz_identity"


def app_of(request: Any) -> Any:
    """The :class:`Bretzel` instance reachable from a raw request.

    ``request.app`` returns the FastAPI; the instance is set on its
    ``state`` by the constructor. Three sites wrote this same climb as
    chained ``getattr`` — here, and twice in ``oauth.py`` — so three
    places to find the day it is set somewhere else.

    Tolerant through ``getattr``: the unit tests' low-level stubs have
    neither ``app`` nor ``state``, and that is the module's convention
    (cf. :func:`request_scheme`).
    """
    return getattr(getattr(getattr(request, "app", None), "state", None), "bretzel", None)


def _from_signed_cookie(request: Any, bretzel: Any) -> str | None:
    """The default source: the ``Bretzel_auth`` cookie ``login`` sets.

    It is not declared by the app and cannot be removed — the rest of the
    framework depends on it (``UserState``, session rotation, writing
    ``request.state.user``). The ``@auth.source`` sources are added behind
    it, they do not replace it.
    """
    key = getattr(getattr(bretzel, "config", None), "_auth_key", None)
    if not key:
        return None
    state = getattr(request, "state", None)
    jar = getattr(state, "cookies", None)
    if not isinstance(jar, dict):
        # Before ``SessionMiddleware``, or outside the Bretzel stack: we
        # read the header back ourselves rather than assume.
        jar = parse_cookies_from_scope(getattr(request, "scope", {}) or {})
    cookie = jar.get(COOKIE_AUTH, "")
    return verify_auth_cookie(cookie, key) if cookie else None


# ───────────────────────────────────────────────────────────────────────────
# Internals — config + request-state shim
# ───────────────────────────────────────────────────────────────────────────


def _auth_key(ctx: object) -> bytes:
    """Pull the derived auth key from ``ctx.app.config``.

    Fails loudly when no config / no key is reachable. **Asymmetric**
    with :func:`render.context.RenderContext._action_key`, which
    silently falls back to empty bytes (action-id rendering can run
    without an attached app in component unit tests, and a bare id
    that won't verify at dispatch time is harmless there). Here in
    auth, signing with an empty key would produce attacker-forgeable
    cookies — ``hmac.new(b"", payload).hexdigest()`` is computable by
    anyone — so we refuse to sign rather than write a cookie nobody
    should trust.
    """
    config = getattr(getattr(ctx, "app", None), "config", None)
    if config is None:
        raise RuntimeError(
            "auth.login/logout needs ctx.app.config — none reachable. "
            "Build a stub via BretzelConfig(secret_key=...) and attach it "
            "to the test app."
        )
    try:
        return config._auth_key
    except AttributeError:
        raise RuntimeError(
            "ctx.app.config has no derived _auth_key. Always go through "
            "BretzelConfig(secret_key=...) so __post_init__ derives the keys."
        ) from None


def _session_max_age_days(ctx: object) -> int:
    config = getattr(getattr(ctx, "app", None), "config", None)
    return int(getattr(config, "session_max_age_days", 30) or 30) if config else 30


def _forget_identity(ctx: object) -> None:
    """Forget the memoised identity — the identity has just changed.

    Without it, a read after ``login()`` in the same request would return
    the previous identity.
    """
    scope = getattr(getattr(ctx, "request", None), "scope", None)
    if isinstance(scope, dict):
        scope.pop(_MEMO, None)


def _attach_user(ctx: object, user: AuthUser | None) -> None:
    """Store ``user`` on the underlying request so app code reaching
    ``request.state.user`` (FastAPI idiom) sees the change without
    going through the framework's ``auth.user_id()`` API."""
    request = getattr(ctx, "request", None)
    if request is not None and hasattr(request, "state"):
        # Tests may use bare ``object()`` as the request stand-in — we
        # don't fail just because state isn't writable.
        with contextlib.suppress(Exception):
            request.state.user = user
