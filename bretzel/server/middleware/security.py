"""Middleware that sets the security headers on every response.

It reads nothing from the request and never blocks: it intercepts
``http.response.start`` and adds its headers to those the response
already carries. The values are decided in
:mod:`bretzel.server.security`; this file only sets them.

**The policy is built once, lazily.** It depends on the URLs the shell
emits — so on knowing whether ``python -m bretzel.render.vendor`` has run
— and on the resolved theme. Both are known from the first response,
never before; computing it when the middleware is built would freeze it
too early. The cost is a single computation per process.

Order: this middleware is **above** the framework stack (just below
compression), so that its headers also cover the responses the layers
below produce on their own — a CSRF 403, an auth 401.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bretzel.server.security import BORING_HEADERS, build_policy

#: ``report-only`` does EVERYTHING but block: the browser evaluates the
#: policy and reports what would have been dropped. It is the first rung,
#: the one that lets a CSP be set on a real app without risking breaking
#: it — you watch what comes back, you complete ``csp_sources``, then you
#: move to ``csp=True``.
_HEADER = {
    True: "content-security-policy",
    "report-only": "content-security-policy-report-only",
}


class SecurityHeadersMiddleware:
    """Set :data:`BORING_HEADERS` and, if asked for, the CSP."""

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
        # The header name depends only on ``csp``, fixed here: reading
        # it back from a module dict on every response gained nothing.
        self._csp_header: str | None = (
            None if csp is False else _HEADER[csp]
        )
        self._policy_cache: str | None = None

    def _policy_value(self) -> str:
        """The policy, computed on the first pass then memoised."""
        if self._policy_cache is None:
            from bretzel.render import shell_sources

            app = self._bretzel_app
            # ``_css_browser_fallback`` is set by ``Bretzel.__init__``
            # then corrected at startup: it holds the requested pipeline,
            # OR ``True`` if the Tailwind compilation failed and we fell
            # back on the browser compiler. We read what the shell reads,
            # not the requested setting — otherwise the policy would
            # block the CDN of a fallback it does not know about.
            #
            # A direct read and not a ``getattr`` with a default: the
            # attribute always exists, and the default we used to write
            # recomputed from the REQUESTED setting, that is to say did
            # exactly what the paragraph above forbids.
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
                # ``MutableHeaders`` is the gesture of the two other
                # middlewares that write on ``http.response.start``
                # (``session``, ``render_context``): it normalises case
                # and encodes to latin-1 itself. Its ``setdefault`` does
                # not overwrite what a route explicitly set — an app that
                # wants its own ``X-Frame-Options`` on a given route
                # keeps it.
                headers = MutableHeaders(scope=message)
                for key, value in self._boring.items():
                    headers.setdefault(key, value)
                if self._csp_header is not None:
                    headers.setdefault(self._csp_header, self._policy_value())
            await send(message)

        await self.app(scope, receive, send_wrapper)
