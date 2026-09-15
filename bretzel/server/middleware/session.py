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
        # ``None`` = déduire du scheme de CHAQUE requête. Le middleware
        # est construit une fois au démarrage, or le transport est une
        # propriété de la requête : la même app peut être atteinte en
        # http et en https (proxy, health-check interne).
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

        # ``auth.login`` / ``auth.logout`` font TOURNER le cookie de
        # session par le pipeline ``new_cookies`` du contexte de rendu —
        # on n'émet le nôtre que si on vient d'en frapper un neuf.
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


#: Le préfixe d'un ``Set-Cookie`` de session, en octets — c'est sous
#: cette forme que les en-têtes voyagent dans un message ASGI.
_SESSION_PREFIX = f"{COOKIE_SESSION}=".encode("latin-1")


def _already_written(message: Message) -> bool:
    """Une couche plus INTERNE a-t-elle déjà posé le cookie de session ?

    Elle seule a raison. Ce middleware est le plus externe, donc son
    ``Set-Cookie`` serait ajouté en DERNIER — et pour un même nom, c'est
    la dernière valeur que le navigateur garde. Sans ce test, une
    connexion sur une requête **sans session préalable** partait avec
    deux ``Set-Cookie: Bretzel_session`` : celui qu'on vient de frapper,
    et celui vers lequel ``auth.login`` a fait tourner la session. Le
    nôtre gagnait.

    Ce n'était pas qu'une inélégance : pendant cette requête, l'état de
    portée session s'écrit sous l'identifiant tourné, celui que le
    navigateur n'allait justement pas garder — donc un brouillon posé
    dans le handler de connexion se perdait à la page suivante. Et la
    rotation anti-fixation, elle, n'était plus qu'une intention.

    Mesuré le 2026-08-24, sur une connexion au tout premier hit :
    deux en-têtes, le second effaçant le premier.
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
