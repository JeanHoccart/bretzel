"""Middleware qui pose les en-têtes de sécurité sur chaque réponse.

Ne lit rien de la requête et ne bloque jamais : il intercepte le
``http.response.start`` et ajoute ses en-têtes à ceux que la réponse
porte déjà. Les valeurs sont décidées dans
:mod:`bretzel.server.security` ; ce fichier ne fait que les poser.

**La politique est construite une fois, paresseusement.** Elle dépend
des URL que la coque émet — donc de savoir si ``python -m
bretzel.render.vendor`` a tourné — et du thème résolu. Les deux sont
connus dès la première réponse, jamais avant ; la calculer à la
construction du middleware la figerait trop tôt. Le coût est d'un seul
calcul par process.

Ordre : ce middleware est **au-dessus** de la pile framework (juste sous
la compression), pour que ses en-têtes couvrent aussi les réponses que
les couches du dessous produisent seules — un 403 CSRF, un 401 auth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bretzel.server.security import BORING_HEADERS, build_policy

#: ``report-only`` fait TOUT sauf bloquer : le navigateur évalue la
#: politique et signale ce qui aurait sauté. C'est le premier barreau,
#: celui qui permet de poser une CSP sur une app réelle sans risquer de
#: la casser — on regarde ce qui remonte, on complète ``csp_sources``,
#: puis on passe à ``csp=True``.
_HEADER = {
    True: "content-security-policy",
    "report-only": "content-security-policy-report-only",
}


class SecurityHeadersMiddleware:
    """Poser :data:`BORING_HEADERS` et, si demandée, la CSP."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        bretzel_app: object,
        boring: bool = True,
        csp: Literal[False, True, "report-only"] = False,
        csp_sources: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.app = app
        self._bretzel_app = bretzel_app
        self._csp = csp
        self._csp_sources = csp_sources or {}
        self._boring: dict[str, str] = dict(BORING_HEADERS) if boring else {}
        # Le nom d'en-tête ne dépend que de ``csp``, fixé ici : le relire
        # dans un dict de module à chaque réponse n'apportait rien.
        self._csp_header: str | None = (
            None if csp is False else _HEADER[csp]
        )
        self._policy_cache: str | None = None

    def _policy_value(self) -> str:
        """La politique, calculée au premier passage puis mémorisée."""
        if self._policy_cache is None:
            from bretzel.render import shell_sources

            app = self._bretzel_app
            # ``_css_browser_fallback`` est posé par ``Bretzel.__init__``
            # puis corrigé au démarrage : il vaut le pipeline demandé, OU
            # ``True`` si la compilation Tailwind a échoué et qu'on est
            # retombé sur le compilateur navigateur. On lit ce que la
            # coque lit, pas le réglage demandé — sinon la politique
            # bloquerait le CDN d'un repli qu'elle ignore.
            #
            # Lecture directe et non ``getattr`` avec défaut : l'attribut
            # existe toujours, et le défaut qu'on écrivait recalculait
            # depuis le réglage DEMANDÉ, c'est-à-dire faisait exactement
            # ce que le paragraphe ci-dessus interdit.
            sources = shell_sources(
                browser_css=app._css_browser_fallback,
                mobile_breakpoint=app.config.mobile_breakpoint,
            )
            self._policy_cache = build_policy(
                inline_bodies=sources.inline,
                script_urls=sources.scripts,
                style_urls=sources.styles,
                extra=self._csp_sources,
            )
        return self._policy_cache

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # ``MutableHeaders`` est le geste des deux autres
                # middlewares qui écrivent sur ``http.response.start``
                # (``session``, ``render_context``) : il normalise la
                # casse et encode en latin-1 lui-même. Son ``setdefault``
                # n'écrase pas ce qu'une route a explicitement posé —
                # une app qui veut son propre ``X-Frame-Options`` sur une
                # route donnée le garde.
                entetes = MutableHeaders(scope=message)
                for cle, valeur in self._boring.items():
                    entetes.setdefault(cle, valeur)
                if self._csp_header is not None:
                    entetes.setdefault(self._csp_header, self._policy_value())
            await send(message)

        await self.app(scope, receive, send_wrapper)
