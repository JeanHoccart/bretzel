"""CSRF middleware — session-bound token + Origin/Referer check.

Reads the per-session CSRF token from the ``X-Bretzel-CSRF`` request
header on every non-safe HTTP method, verifies it against the value
the server expects for the active session, and rejects mismatches
with a ``403``.

The token is computed deterministically as ::

    csrf_token = hmac(csrf_key, session_id)[:32]

where ``csrf_key`` is :func:`derive_key(secret_key, PURPOSE_CSRF)
<bretzel.server.crypto.derive_key>` and ``session_id`` is the value
of the ``Bretzel_session`` cookie populated by
:class:`SessionMiddleware <bretzel.server.middleware.session.SessionMiddleware>`.
The page render pipeline injects the same token into the envelope as
``$bz._csrf`` (:attr:`RenderContext.csrf_token
<bretzel.render.context.RenderContext.csrf_token>`) ; the runtime
echoes it back from the bridge
(:file:`runtime/_src/05_bridge.js`).

**Why this works as CSRF protection** — the browser auto-sends the
session cookie cross-origin, but cannot read it (HttpOnly) ; cross-
origin scripts cannot set the ``X-Bretzel-CSRF`` header without a
CORS preflight that we never grant. An attacker who lures the victim
into a malicious page therefore cannot compute the expected token
without first leaking ``session_id`` AND ``csrf_key`` (server-only) —
both required, impossible from a hostile origin.

**Skipped paths** — ``/_bretzel/action/*`` uses its own per-call
HMAC on ``action_id + bound_args`` (cf.
:mod:`bretzel.server.handlers`) which already binds the request to
something only the page render could have signed. Re-checking CSRF on
top would be redundant ; this middleware short-circuits action routes
so the dispatcher remains the single auth point there.

"""

from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from bretzel.runtime.protocol import HEADER_CSRF, ROUTE_ACTION
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.middleware._state import ensure_state

# Methods that mutate server state and therefore need CSRF protection.
# GET / HEAD / OPTIONS / TRACE are "safe" per RFC 9110 ; we let them
# through unchecked.
_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Pre-encoded ASGI header keys (ASGI normalises to lowercase bytes).
_CSRF_HEADER_KEY = HEADER_CSRF.lower().encode("latin-1")
_ORIGIN_KEY = b"origin"
_REFERER_KEY = b"referer"
_HOST_KEY = b"host"

# Truncation width of the token. 32 hex chars (~128 bits) — well above
# brute-force resistance for a per-session value, short enough to keep
# the envelope and headers compact.
_CSRF_TOKEN_LEN = 32


def csrf_token_for(session_id: str, csrf_key: bytes) -> str:
    """Compute the CSRF token for ``session_id`` under ``csrf_key``.

    Used both by the render pipeline (to inject into the envelope) and
    by this middleware (to validate the inbound header). Deterministic
    on ``session_id`` so refreshes don't invalidate in-flight tokens
    as long as the session cookie doesn't rotate.
    """
    if not session_id:
        return ""
    return _crypto_sign(csrf_key, session_id, hex_len=_CSRF_TOKEN_LEN)


class CSRFMiddleware:
    """Verify the per-session CSRF token on non-safe HTTP methods.

    Always-on : there is no ``csrf=False`` knob on :class:`BretzelConfig`.
    Apps that need an unprotected POST endpoint (webhook receivers,
    OAuth callbacks) should expose it outside the Bretzel router or
    explicitly handle auth there with a different mechanism — CSRF is
    a browser-origin defence and doesn't apply to server-to-server.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        csrf_key: bytes,
        trusted_hosts: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self._csrf_key = csrf_key
        # Lower-cased once at construction so the per-request hostname
        # comparison is direct case-insensitive equality. Wildcards
        # (``*.example.com``) are accepted as a literal prefix match
        # against the leading dot — same convention as Starlette's
        # :class:`TrustedHostMiddleware`.
        self._trusted_hosts: tuple[str, ...] = tuple(
            h.lower() for h in trusted_hosts
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        if method not in _PROTECTED_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Action route — HMAC on ``action_id + bound_args`` already
        # binds the call to render-time signing. Re-checking CSRF here
        # is redundant and would force the dispatcher to ship a token
        # it doesn't need.
        if path.startswith(ROUTE_ACTION + "/"):
            await self.app(scope, receive, send)
            return

        # Single-pass scan of the ASGI headers list — avoids the
        # per-request ``dict()`` alloc, picks up only the four entries
        # we care about. Headers are normalised to lowercase bytes by
        # the ASGI server.
        origin_b = b""
        referer_b = b""
        host_b = b""
        supplied_b = b""
        for k, v in scope.get("headers", ()):
            if k == _ORIGIN_KEY:
                origin_b = v
            elif k == _REFERER_KEY:
                referer_b = v
            elif k == _HOST_KEY:
                host_b = v
            elif k == _CSRF_HEADER_KEY:
                supplied_b = v

        # 1. Origin / Referer same-origin (or trusted-host) check.
        if not self._origin_allowed(origin_b, referer_b, host_b):
            await _reject(send, "CSRF: untrusted origin")
            return

        # 2. Session-bound token check.
        state = ensure_state(scope)
        session_id = getattr(state, "session_id", "") or ""
        supplied = supplied_b.decode("latin-1")
        expected = csrf_token_for(session_id, self._csrf_key)
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            await _reject(send, "CSRF: token missing or invalid")
            return

        await self.app(scope, receive, send)

    # ── Internals ────────────────────────────────────────────────────────

    def _origin_allowed(
        self, origin_b: bytes, referer_b: bytes, host_b: bytes
    ) -> bool:
        """Compare the request's ``Origin`` / ``Referer`` host to the
        request's ``Host`` (and any configured ``trusted_hosts``).

        Returns ``True`` when no Origin/Referer is present — some
        legitimate clients (curl, server-to-server) don't send either,
        and we don't want to reject every non-browser caller. The
        token check downstream is the real defence ; this is
        belt-and-suspenders for the cross-origin browser case.
        """
        origin = origin_b.decode("latin-1") or referer_b.decode("latin-1")
        if not origin:
            return True

        try:
            origin_host = urlsplit(origin).hostname or ""
        except ValueError:
            return False
        origin_host = origin_host.lower()
        if not origin_host:
            return False

        # Same-origin : Origin's hostname matches the request's Host.
        # Host header includes ``:port`` ; strip for hostname compare.
        host_only = host_b.decode("latin-1").lower().split(":", 1)[0]
        if origin_host == host_only:
            return True

        # Configured trusted hosts — exact match or ``*.suffix`` glob.
        for trusted in self._trusted_hosts:
            if trusted.startswith("*."):
                if origin_host.endswith(trusted[1:]):
                    return True
            elif origin_host == trusted:
                return True

        return False


async def _reject(send: Send, detail: str) -> None:
    """Emit a minimal ``403 Forbidden`` response directly via ASGI.

    We don't go through a :class:`~starlette.responses.Response` here
    — the early-reject path doesn't need template / cookie support, so
    two ``send`` calls are cheaper and have no fake-scope smell.

    Body is a ``_error: reload`` envelope (same as the action route's bad
    sig) : a rejected POST is almost always a stale / missing CSRF token,
    and re-rendering the page mints a fresh one — so the bridge reloads
    rather than showing a dead-end generic toast.
    """
    from bretzel.runtime.envelope import error_envelope

    body = error_envelope("reload", detail).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
