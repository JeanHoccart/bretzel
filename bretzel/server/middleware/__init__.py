"""Framework middlewares wrapping the underlying FastAPI.

Inbound order (outermost → innermost) :

0. :class:`SecurityHeadersMiddleware <.security.SecurityHeadersMiddleware>`
   — pose les en-têtes de sécurité sur la réponse au retour. Le plus
   externe des cinq pour couvrir aussi ce que les couches du dessous
   produisent seules (un 403 CSRF, un 401 auth).
1. :class:`SessionMiddleware <.session.SessionMiddleware>` — mints /
   reads the ``Bretzel_session`` cookie ; stashes ``session_id`` and
   parsed cookies on ``request.state``.
2. :class:`CSRFMiddleware <.csrf.CSRFMiddleware>` — verifies the
   per-session ``X-Bretzel-CSRF`` header on non-safe HTTP methods.
   Skipped for ``/_bretzel/action/*`` (those carry their own HMAC).
3. :class:`AuthMiddleware <.auth.AuthMiddleware>` — verifies the
   ``Bretzel_auth`` cookie and pins ``request.state.user``.
4. :class:`RenderContextMiddleware <.render_context.RenderContextMiddleware>`
   — composes the :class:`~bretzel.render.context.RenderContext` that
   the rest of the pipeline reads from ; buffers + parses the form
   body once and splits the V3 namespaced client-state fields
   (``Class.key.field``) from regular handler args.
"""
