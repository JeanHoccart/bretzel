"""Session-cookie middleware — `Bretzel_session`.

Tiny on purpose : the session id is just a random opaque string the
state registry uses to scope per-session storage. No payload, no
signing — Starlette's :class:`SessionMiddleware` would be overkill
for what we need.

Outermost framework middleware in inbound order : also parses the
inbound ``Cookie`` header once and stashes it on
``request.state.cookies`` so the auth middleware doesn't re-parse.
"""

from __future__ import annotations

import secrets

from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bretzel.server.auth import (
    COOKIE_SESSION,
    parse_cookies_from_scope,
    resolve_cookie_secure,
)
from bretzel.server.middleware._state import ensure_state


class SessionMiddleware:
    """Read or mint the ``Bretzel_session`` cookie on every request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_age_seconds: int,
        secure: bool | None,
    ) -> None:
        self.app = app
        self._max_age = max_age_seconds
        # ``None`` = derive from EACH request's scheme. The middleware
        # is built once at startup, and the transport is a property of
        # the request: the same app can be reached over http and over
        # https (proxy, internal health check).
        self._secure_override = secure

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cookies = parse_cookies_from_scope(scope)
        existing = cookies.get(COOKIE_SESSION)
        if existing:
            session_id = existing
            mint_fresh = False
        else:
            session_id = secrets.token_hex(16)
            mint_fresh = True

        state = ensure_state(scope)
        state.cookies = cookies
        state.session_id = session_id

        if not mint_fresh:
            await self.app(scope, receive, send)
            return

        # ``auth.login`` / ``auth.logout`` ROTATE the session cookie
        # through the render context's ``new_cookies`` pipeline — we only
        # emit ours when we have just minted a fresh one.
        cookie_header = _format_session_cookie(
            session_id,
            max_age=self._max_age,
            secure=resolve_cookie_secure(
                scope.get("scheme"), self._secure_override
            ),
        )

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start" and not _already_written(
                message
            ):
                MutableHeaders(scope=message).append("set-cookie", cookie_header)
            await send(message)

        await self.app(scope, receive, send_with_cookie)


#: The prefix of a session ``Set-Cookie``, in bytes — that is the form
#: headers travel in inside an ASGI message.
_SESSION_PREFIX = f"{COOKIE_SESSION}=".encode("latin-1")


def _already_written(message: Message) -> bool:
    """Has a more INNER layer already set the session cookie?

    It alone is right. This middleware is the outermost, so its
    ``Set-Cookie`` would be added LAST — and for one name, it is the last
    value the browser keeps. Without this test, a sign-in on a request
    **with no prior session** went out with two
    ``Set-Cookie: Bretzel_session``: the one we had just minted, and the
    one ``auth.login`` had rotated the session to. Ours won.

    That was not merely inelegant: during that request, session-scoped
    state is written under the rotated identifier, the very one the
    browser was not going to keep — so a draft set in the sign-in handler
    was lost on the next page. And the anti-fixation rotation was no more
    than an intention.

    Measured on 2026-08-24, on a sign-in at the very first hit: two
    headers, the second erasing the first.
    """
    return any(
        key == b"set-cookie" and value.startswith(_SESSION_PREFIX)
        for key, value in message.get("headers", ())
    )


def _format_session_cookie(value: str, *, max_age: int, secure: bool) -> str:
    """Build the ``Set-Cookie`` header value via Starlette's own formatter.

    Delegating to a throwaway :class:`Response` keeps us bit-identical
    to whatever ``Response.set_cookie`` writes everywhere else — no
    drift between the session middleware and the
    ``RenderContext.new_cookies`` outbound path.
    """
    dummy = Response()
    dummy.set_cookie(
        COOKIE_SESSION,
        value,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    for k, v in dummy.raw_headers:
        if k == b"set-cookie":
            return v.decode("latin-1")
    raise RuntimeError("Response.set_cookie produced no Set-Cookie header")
