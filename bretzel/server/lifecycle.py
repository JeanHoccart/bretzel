"""Startup / shutdown orchestration.

Called from :py:meth:`Bretzel._lifespan`. The order matters :

**Startup**
1. Resolve theme + generate ``theme.css`` (cached on the app).
2. Pick a state backend (in-memory if no Redis URL ; multi-worker
   without Redis fails fast).
3. Mount static / page / action routes on the underlying FastAPI.
4. Build the middleware stack (framework internals first, user
   middlewares wrap the lot).
5. Run user-registered ``@app.startup`` hooks.

**Shutdown**
1. Run user-registered ``@app.shutdown`` hooks (LIFO).
2. Close the state backend (if it has an ``aclose`` / ``close``).

"""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bretzel.core import call_without_blocking
from bretzel.runtime.protocol import ROUTE_STATIC_DIR
from bretzel.server.errors import BretzelError
from bretzel.server.middleware.auth import AuthMiddleware
from bretzel.server.middleware.csrf import CSRFMiddleware
from bretzel.server.middleware.render_context import RenderContextMiddleware
from bretzel.server.middleware.security import SecurityHeadersMiddleware
from bretzel.server.middleware.session import SessionMiddleware
from bretzel.server.routing.actions import register_action_route
from bretzel.server.routing.datatable import register_datatable_export_route
from bretzel.server.routing.downloads import register_download_routes
from bretzel.server.routing.manifest import register_manifest_route
from bretzel.server.routing.pages import register_pages
from bretzel.server.routing.realtime import register_realtime_route
from bretzel.server.routing.sse import register_sse_route
from bretzel.server.routing.static import register_static_routes
from bretzel.server.sse import MemoryBroker
from bretzel.state.persistence.base import Backend
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.theme import strip_safelist, strip_scan_roots

if TYPE_CHECKING:
    from bretzel.server.app import Bretzel


# ───────────────────────────────────────────────────────────────────────────
# Startup
# ───────────────────────────────────────────────────────────────────────────


_log = logging.getLogger("bretzel.server.lifecycle")

async def _check_state_backend(app: Bretzel) -> None:
    """Fail FAST when the state backend is unreachable.

    The ``StateBackend.health()`` contract had announced "Called once at
    app startup" forever — with no caller at all (verified 2026-08-01). A
    wrong Redis URL therefore produced an obscure error on the FIRST user
    request, instead of a readable refusal to start.

    We do NOT raise on a backend answering ``False`` without an
    exception: a negative ``health`` can be transient (Redis restarting),
    and bringing the process down over it would make the boot more
    fragile than the runtime. We raise on an **exception** — invalid URL,
    dead DNS, connection refused — because that one does not repair
    itself.
    """
    backend = getattr(app, "_state_backend", None)

    # The protocol is STRUCTURAL: nothing at definition time forces an
    # implementation to be complete, and the gap only shows at call time
    # — for ``merge``, at the end-of-request commit, that is to say in
    # production. ``Backend`` is ``runtime_checkable``, so the check
    # costs one line and turns a crash into a refusal to start. It only
    # bites on a THIRD-PARTY backend: the repository's two pass it by
    # construction.
    if backend is not None and not isinstance(backend, Backend):
        missing = sorted(
            name
            for name in vars(Backend)
            if not name.startswith("_") and not hasattr(backend, name)
        )
        raise RuntimeError(
            f"The state backend ({type(backend).__name__}) does not "
            f"implement the whole Backend protocol: {missing} are missing. "
            f"Without this check, the absence would only have raised on the "
            f"first call — for ``merge``, at the end of the first request "
            f"that writes a state."
        )

    check = getattr(backend, "health", None)
    if not callable(check):
        return
    try:
        ok = await check()
    except Exception as exc:  # re-raised enriched just below
        raise RuntimeError(
            f"The state backend ({type(backend).__name__}) is unreachable "
            f"at startup: {exc!r}. Check the URL / credentials passed to "
            f"`Bretzel(...)`. (Without this check, the error would only have "
            f"appeared on the first request.)"
        ) from exc
    if not ok:
        _log.warning(
            "The state backend (%s) answers health()=False at startup — "
            "the app starts anyway (it may be transient), but persisted "
            "states risk not surviving.",
            type(backend).__name__,
        )


async def bretzel_startup(app: Bretzel) -> None:
    """Run framework-side startup. Call before user hooks.

    Middleware registration is NOT done here — Starlette freezes its
    stack on the first ASGI call, lifespan included, so a startup hook
    arrives too late.

    ⚠️ The opposite conclusion — "so the constructor calls it" — was
    written here and applied until 2026-08-15. It froze the stack BEFORE
    user code could run, since one writes ``@app.middleware`` after
    ``app = Bretzel(...)``. Result: ``@app.middleware`` was a **complete
    no-op**. Building is now deferred to ``Bretzel.__call__``, the only
    moment when the user module is imported and Starlette has frozen
    nothing.
    """
    _validate_theme(app)
    _resolve_theme(app)
    _build_state_backend(app)
    await _check_state_backend(app)
    _build_sse_broker(app)
    # Every broker honours the SSEBroker lifecycle contract : MemoryBroker's
    # ``start`` is a no-op, RedisBroker subscribes + spins its listener.
    await app._sse_broker.start()
    _build_idempotency_store(app)
    _register_routes(app)
    await _run_user_hooks(app, getattr(app, "_startup_hooks", []) or [])
    app._is_ready = True


async def bretzel_shutdown(app: Bretzel) -> None:
    """Run framework-side teardown. Call after user hooks (LIFO)."""
    app._is_ready = False
    await _run_user_hooks(
        app, list(reversed(getattr(app, "_shutdown_hooks", []) or []))
    )
    # Tear down the SSE broker first — its Redis listener holds a live
    # Pub/Sub connection that must be cancelled before the loop closes.
    # ``aclose`` is part of the SSEBroker contract (no-op on MemoryBroker).
    broker = getattr(app, "_sse_broker", None)
    if broker is not None:
        await broker.aclose()
    backend = getattr(app, "_state_backend", None)
    if backend is not None:
        for closer in ("aclose", "close"):
            fn = getattr(backend, closer, None)
            if callable(fn):
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
                break


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _validate_theme(app: Bretzel) -> None:
    """Refuse a theme override nothing will read — **before** anything else.

    The first call of the startup, and that is deliberate: what follows
    compiles CSS, opens a state backend, mounts routes. Failing later
    would have cost that work for nothing, and above all would have mixed
    the message into initialisation traces.

    Why here and not in ``Theme.__init__``: the vocabulary is derived
    from the component classes, and the ``theme`` layer may not import
    them (the ``base-independent-of-app`` contract). Startup is the first
    place where both halves coexist — exactly like ``color_shapes`` just
    below. A ``Theme`` built on its own (a test, a script) therefore stays
    valid without the components layer: that is what keeps it testable in
    isolation, and it is the accepted price of the asymmetry with
    ``semantic=``, which does raise at construction.

    Deferred imports: ``introspect`` is layer 7 and must not weigh on the
    server's load order (an idiom already applied to ``components`` in
    ``_resolve_theme``).
    """
    from bretzel.introspect import theme_vocabulary
    from bretzel.introspect.packages import third_party_theme_vocabulary
    from bretzel.theme.slots import validate_component_overrides

    theme = app.theme
    if theme is None:
        return
    # ⚠️ The vocabulary is the framework's **plus** that of the
    # installed packages. Without the second half, a third-party library
    # can publish slots the app installing it cannot override: all it has
    # left is ``classes=`` at the call site, repeated everywhere, with no
    # cascade and no dark-theme consistency. That is the difference
    # between a themed component and copied HTML.
    #
    # The order matters: third parties override — but they CANNOT
    # collide, ``third_party_theme_vocabulary`` raises first.
    vocabulary = {**theme_vocabulary(), **third_party_theme_vocabulary()}
    validate_component_overrides(theme.get_component_overrides(), vocabulary)


def _resolve_theme(app: Bretzel) -> None:
    """Generate theme.css once and stash on the app.

    This is where we inject what the component themes know and the
    Tailwind scanner cannot guess — colour templates AND the tokens of
    the graded props: the first point in the stack allowed to see both
    ``theme`` (base) and ``components`` (application), cf.
    ``bretzel/components/color_shapes.py``.

    Two variants come out of here, because the two consumers do not have
    the same needs:

    - ``_theme_css_content`` — with the safelist. That is what the
      production compiler ingests, and what ``/_bretzel/theme.css``
      serves.
    - ``_theme_css_inline`` — without the safelist. That is the
      ``<style type="text/tailwindcss">`` block inlined into EVERY page
      in dev, where the browser compiler scans the DOM and therefore has
      no need of the safelist. Leaving it there cost 69 KB per page
      (66 % of the document) and as many rules to generate before the
      first styled render.
    """
    from bretzel.components import (
        dynamic_responsive_classes,
    )

    full = app.theme.generate_css(
        responsive_classes=dynamic_responsive_classes(),
    )
    app._theme_css_content = full
    app._theme_css_inline = strip_safelist(full)


def _build_state_backend(app: Bretzel) -> None:
    """Choose the persistence backend.

    No Redis URL → in-memory (single-worker dev). Multi-worker without
    Redis is rejected by the config at construction, so the only
    branch we need to handle here is "Redis URL is set".
    """
    config = app.config
    if config.redis_url:
        # Redis import is deferred so test environments without the
        # ``redis`` package can still build a Bretzel app on memory.
        from bretzel.state.persistence.redis import RedisBackend

        app._state_backend = RedisBackend.from_url(config.redis_url)
    else:
        app._state_backend = MemoryBackend()


def _build_sse_broker(app: Bretzel) -> None:
    """Wire the SSE broker for ``@refreshable(deps=[…], broadcast=[State])``.

    Redis URL set → cross-worker :class:`RedisBroker` (Pub/Sub fanout of
    the ``state-dirty`` signal) ; otherwise the in-process
    :class:`MemoryBroker`. Branching on ``redis_url`` alone (not
    ``workers>1``) mirrors the state backend and idempotency store : a
    shared Redis is the signal that other processes/replicas may hold the
    subscribing tabs, and the config already forces a ``redis_url`` when
    ``workers>1``.
    """
    config = app.config
    if config.redis_url:
        # Deferred import so memory-only apps don't need the redis package.
        from bretzel.server.sse import RedisBroker

        app._sse_broker = RedisBroker.from_url(config.redis_url)
    else:
        app._sse_broker = MemoryBroker()


def _build_idempotency_store(app: Bretzel) -> None:
    """Wire the ``@idempotent`` dedup store — Redis when a URL is set (its
    atomic ``SET NX`` is what a multi-worker claim needs), else in-memory.
    """
    config = app.config
    if config.redis_url:
        from bretzel.server.idempotency import RedisIdempotencyStore

        app._idempotency_store = RedisIdempotencyStore.from_url(config.redis_url)
    else:
        from bretzel.server.idempotency import MemoryIdempotencyStore

        app._idempotency_store = MemoryIdempotencyStore()


def _mount_static_dir(app: Bretzel) -> None:
    """Mount ``config.static_dir`` at ``/static``, if the app declares one.

    ``static_dir`` was accepted in ``Bretzel(...)``'s signature, stored
    in the config, and documented as "mounted at ``/static`` on the
    underlying FastAPI" — with no ``.mount()`` existing anywhere in the
    repository (verified 2026-08-01). A user passing it therefore
    received **nothing**, silently: worse than an absent kwarg, which
    would have raised for them. Wired rather than removed — serving a
    favicon or a logo is a battery one asks for on day one.

    A declared but missing folder **raises at startup**: it is a path
    typo, and it does not repair itself.
    """
    raw = app.config.static_dir
    if not raw:
        return
    directory = Path(raw)
    if not directory.is_dir():
        raise RuntimeError(
            f"`Bretzel(static_dir={raw!r})` does not point at an existing "
            f"folder (resolved: {directory.resolve()}). Fix the path, "
            f"ou retire l'argument."
        )
    from starlette.staticfiles import StaticFiles

    # ``check_dir=False``: we have just checked it, with a more useful
    # message than Starlette's.
    app.fastapi.mount(
        ROUTE_STATIC_DIR,
        StaticFiles(directory=directory, check_dir=False),
        name="bretzel_static",
    )


def _register_routes(app: Bretzel) -> None:
    """Attach static / pages / actions routes to ``app.fastapi``."""
    runtime_js_path = (
        Path(__file__).resolve().parent.parent / "runtime" / "runtime.js"
    )

    # ``css_pipeline`` (and not the mode) decides: ``build`` compiles
    # ``style.css`` with the Tailwind binary and serves it as a
    # ``<link>``; ``browser`` lets the browser compiler do the work in
    # the page. Cf. ``config.css`` for the trade-off.
    style_css = ""
    app._css_browser_fallback = app.config.css_pipeline == "browser"
    if app.config.css_pipeline == "build" and app._theme_css_content:
        from bretzel.theme.build import get_or_build_css
        from bretzel.theme.compiler import CompilerError

        try:
            # In dev, we always recompile. The cache is keyed on the
            # THEME's fingerprint: a Tailwind class freshly written in
            # user code does not change it, so the cache would make it
            # disappear from the CSS — silently, which is precisely the
            # failure mode we are hunting. Whoever asks for
            # ``css="build"`` in dev has already accepted paying for the
            # compilation; it may as well be correct.
            style_css = get_or_build_css(
                app._theme_css_content, rebuild=app.config.is_dev
            )
        except CompilerError as exc:
            # Startup does not block, but we do NOT serve a bare page:
            # we fall back explicitly on the browser compiler, and say
            # so. A silent fallback would make the render diverge from
            # production without anyone knowing — that is exactly how a
            # truncated safelist went unnoticed for months.
            app._css_browser_fallback = True
            print(
                f"[bretzel] WARN: Tailwind compilation impossible — {exc}\n"
                "[bretzel]        falling back on the browser compiler: the "
                "render may differ from production.\n"
                "[bretzel]        install the binary with "
                "``pip install 'bretzel[css]'``."
            )

    register_static_routes(
        app.fastapi,
        runtime_js_path=runtime_js_path,
        # ``strip_scan_roots``: this route is public and serves the
        # theme "for inspection". The scan roots are ABSOLUTE server
        # paths — they have no business in an HTTP response, and the
        # browser compiler does nothing with them.
        theme_css=strip_scan_roots(app._theme_css_content),
        style_css=style_css,
        # Cache headers = assets axis, not diagnostics.
        dev=app.config.is_dev,
    )
    _mount_static_dir(app)
    register_pages(app.fastapi, app)
    _mount_login_doors(app)
    register_action_route(app.fastapi, app)
    register_datatable_export_route(app.fastapi, app)
    register_download_routes(app.fastapi, app, app._downloads)
    register_manifest_route(app.fastapi, app)
    register_sse_route(app.fastapi, app)
    register_realtime_route(app.fastapi, app)


def _mount_login_doors(app: Bretzel) -> None:
    """Mount the doors declared with ``@auth.door``.

    Here and not at ``include()`` for the same reason as the pages: the
    router is read on every request, but the ASGI stack freezes on the
    first call — startup is the last moment when all user code has been
    imported and nothing is being served yet.
    """
    for door, on_user in app.doors:
        door.mount(app, on_user)


def build_middleware_stack(app: Bretzel) -> None:
    """Wrap the FastAPI app in framework + user middlewares.

    Inbound flow (outermost → innermost):

    - User middlewares (registration order, wrapped LIFO so first
      registered ends up outermost).
    - ``GZipMiddleware`` (gzip level 6; SSE is excluded by content type).
    - Trusted hosts / CORS — Starlette stock, opt-in via config.
    - ``SessionMiddleware`` (mints / reads ``Bretzel_session``).
    - ``CSRFMiddleware`` (verifies ``X-Bretzel-CSRF`` on non-safe
      methods using the session id Session just populated;
      short-circuits ``/_bretzel/action/*`` since those carry their
      own HMAC).
    - ``AuthMiddleware`` (reads the auth cookie).
    - ``RenderContextMiddleware`` (innermost — composes a
      :class:`RenderContext` from everything the upstream middleware
      just wrote on ``request.state``, buffers + parses the form body
      once, splits the V3 namespaced client-state fields from handler
      args).

    Starlette's ``add_middleware`` registers innermost-first (last-added
    is outermost on inbound), so the calls below are in reverse of the
    inbound flow.
    """
    config = app.config

    # Innermost — RenderContextMiddleware reads what every upstream
    # middleware wrote on ``request.state`` and ties it on a new
    # RenderContext. Must run AFTER session/auth.
    app.fastapi.add_middleware(RenderContextMiddleware, bretzel_app=app)

    # AuthMiddleware reads ``request.state.session_id`` (populated by
    # SessionMiddleware upstream) and verifies the ``Bretzel_auth``
    # cookie with the *derived* auth key, not the master secret.
    app.fastapi.add_middleware(AuthMiddleware, bretzel_app=app)

    # CSRFMiddleware reads the session id Session set on
    # ``request.state``, computes the expected token, and rejects
    # non-safe-method requests whose ``X-Bretzel-CSRF`` header doesn't
    # match. Action routes (``/_bretzel/action/*``) are bypassed —
    # they carry their own per-call HMAC.
    app.fastapi.add_middleware(
        CSRFMiddleware,
        csrf_key=config._csrf_key,
        trusted_hosts=config.trusted_hosts,
    )

    # SessionMiddleware — outermost framework layer ; mints the
    # session cookie and exposes it on ``request.state.session_id``.
    app.fastapi.add_middleware(
        SessionMiddleware,
        max_age_seconds=config.session_max_age_days * 86400,
        # ``None`` = the middleware derives it from the scheme, per
        # request.
        secure=config.secure_cookies,
    )

    # Optional CORS / TrustedHost. Both are no-ops without config.
    if config.trusted_hosts:
        app.fastapi.add_middleware(
            TrustedHostMiddleware, allowed_hosts=list(config.trusted_hosts)
        )
    if config.cors_origins:
        app.fastapi.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Compression — the OUTERMOST framework layer, so it sees the final
    # body, after everything else has written.
    #
    # Bretzel's HTML is repetitive BY CONSTRUCTION: the same Tailwind
    # class string on every instance of a component, the same ``bz-*``
    # expression on every control of the same kind. Measured on the
    # playground's ``/datatable`` (2026-08-07): 9 085 ``class``
    # attributes for 328 distinct strings, so 97 % duplicates — and
    # ``class=`` + ``bz-*`` together make up ~80 % of a page's bytes.
    # That is exactly what a compressor eats: 1 334 KB → 91 KB.
    #
    # Level 6 and not 9 (Starlette's default): 5.9 ms of CPU for this
    # page against 113 ms to render it, and 9 only gains 2 KB more. The
    # scale is flat beyond 6.
    #
    # ⚠️ The SSE stream must NEVER be compressed — ``apply_compression``
    # only flushes its zlib buffer on the last chunk, and a stream has
    # none, so every event would stay held indefinitely, with no error
    # and no trace. Starlette 1.3 already excludes it by content type
    # (``DEFAULT_EXCLUDED_CONTENT_TYPES``), which is better than a
    # path-based exclusion: it also covers a stream an app would expose
    # elsewhere. We DEPEND on it, so we GATE it —
    # ``tests/integration/server/test_compression.py``.
    app.fastapi.add_middleware(GZipMiddleware, compresslevel=6)

    # Security headers — above the whole framework stack (so added
    # AFTER it) to also cover the responses the layers below produce on
    # their own: a CSRF 403, an auth 401, an error page. Below
    # compression, which stays the outermost.
    #
    # The boring headers are a default, the CSP is not: cf.
    # :mod:`bretzel.server.security` for why the line falls there.
    if config.security_headers or config.csp is not False:
        app.fastapi.add_middleware(
            SecurityHeadersMiddleware,
            bretzel_app=app,
            boring=config.security_headers,
            csp=config.csp,
            csp_sources=config.csp_sources,
        )

    # 1 → user middlewares last so they wrap everything above.
    #
    # ``reversed`` because ``add_middleware`` registers innermost-first
    # (the LAST added is the outermost). Walking the list in order, the
    # last ``@app.middleware`` written became the outermost — the
    # opposite of what ``decorators/middleware.py`` promises: "first
    # registered = outermost". Nobody had seen it because no user
    # middleware ran at all before 2026-08-15.
    #
    # It is the promise we hold, not the implementation's accident: it is
    # the convention of a list written top to bottom (Django's
    # ``MIDDLEWARE`` reads that way), and it is the one that makes an
    # auth guard written first actually cover.
    for user_mw in reversed(getattr(app, "_user_middlewares", None) or []):
        if inspect.isclass(user_mw):
            app.fastapi.add_middleware(user_mw)
        else:
            # Callable async dispatch — wrap with BaseHTTPMiddleware.
            from starlette.middleware.base import BaseHTTPMiddleware

            # ``_mw=user_mw`` binds THIS iteration's value. A bare
            # closure would read ``user_mw`` when dispatch is called, so
            # after the loop has ended: with two callable middlewares,
            # both classes would call the LAST one, and the first would
            # never run. Silent — the request goes through, the missing
            # middleware does not report itself.
            class _UserMw(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next, _mw=user_mw):  # type: ignore[no-untyped-def]
                    return await _mw(request, call_next)

            app.fastapi.add_middleware(_UserMw)


async def _run_user_hooks(app: Bretzel, hooks: list) -> None:
    for hook in hooks:
        try:
            # Offloaded when synchronous (cf. ``core/invoke``): a
            # startup hook migrating a schema or filling a cache
            # otherwise blocks the loop while uvicorn says it is ready.
            await call_without_blocking(hook)
        except Exception as exc:  # surface any startup failure
            raise BretzelError(
                f"Lifecycle hook {hook!r} failed : {exc}"
            ) from exc
