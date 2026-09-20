"""Identity middleware — resolves ``request.state.user`` on every request.

It delegates reading the identity to
:func:`bretzel.server.auth.resolve_identity`, which plays the chain — the
signed cookie first, then the sources the app declared with
``@auth.source`` (a bearer JWT, an API key, an SSO proxy's header).

The layer-5 helpers (:func:`user_id`, :func:`is_authenticated`) read
``state.user_id`` back through the active :class:`RenderContext`.

A tampered, expired or absent cookie — and a source that recognises
nothing — all come out as "anonymous", not as an error. Showing a 401 on
a public page would be wrong; it is the page that decides whether it
requires an identity (through ``UserState`` or an explicit
``abort(401)``).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from bretzel.server.auth import AuthUser, resolve_identity
from bretzel.server.middleware._state import ensure_state


class AuthMiddleware:
    """Resolve ``request.state.user`` from the identity chain."""

    def __init__(self, app: ASGIApp, *, bretzel_app: object) -> None:
        self.app = app
        self._bretzel = bretzel_app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = ensure_state(scope)
        # ``Request`` is only a view onto the scope — no body read
        # here, so no need for ``receive``. The sources read headers and
        # cookies there; ``SessionMiddleware``, further out, has already
        # filled ``state.cookies``.
        request = Request(scope)
        # The app is passed explicitly rather than read back from
        # ``scope["app"]``: this middleware can be mounted on a test
        # stack with no FastAPI above it, and an identity resolution that
        # depended on how we are mounted would be exactly the kind of
        # silence this subject does not tolerate.
        user_id = resolve_identity(request, self._bretzel)
        state.user = AuthUser(id=user_id) if user_id else None
        state.user_id = user_id

        await self.app(scope, receive, send)
