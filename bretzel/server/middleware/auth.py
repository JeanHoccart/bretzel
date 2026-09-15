"""Identity middleware — résout ``request.state.user`` à chaque requête.

Il délègue la lecture de l'identité à
:func:`bretzel.server.auth.resolve_identity`, qui joue la chaîne — le
cookie signé d'abord, puis les sources déclarées par l'app avec
``@auth.source`` (JWT porté, clé d'API, en-tête d'un proxy SSO).

Les helpers de la couche 5 (:func:`user_id`, :func:`is_authenticated`)
relisent ``state.user_id`` via le :class:`RenderContext` actif.

Cookie trafiqué, expiré ou absent — et source qui ne reconnaît rien —
sortent tous en « anonyme », pas en erreur. Afficher un 401 sur une page
publique serait faux ; c'est la page qui décide si elle exige une
identité (via ``UserState`` ou un ``abort(401)`` explicite).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from bretzel.server.auth import AuthUser, resolve_identity
from bretzel.server.middleware._state import ensure_state


class AuthMiddleware:
    """Résout ``request.state.user`` depuis la chaîne d'identité."""

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
        # ``Request`` n'est qu'une vue sur le scope — aucune lecture de
        # corps ici, donc pas besoin de ``receive``. Les sources y
        # lisent en-têtes et cookies ; ``SessionMiddleware``, plus
        # externe, a déjà rempli ``state.cookies``.
        request = Request(scope)
        # L'app est passée en clair plutôt que relue dans ``scope["app"]``
        # : ce middleware peut être monté sur une pile de test sans
        # FastAPI au-dessus, et une résolution d'identité qui dépendrait
        # de la façon dont on est monté serait exactement le genre de
        # silence que ce sujet ne supporte pas.
        user_id = resolve_identity(request, self._bretzel)
        state.user = AuthUser(id=user_id) if user_id else None
        state.user_id = user_id

        await self.app(scope, receive, send)
