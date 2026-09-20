"""``Bretzel`` — the user-facing app class.

A single, opinionated entry point that wraps FastAPI :

    app = Bretzel(secret_key="...", theme=my_theme)

    @page("/")
    def home(): ...

    @app.middleware
    async def log_requests(request, call_next): ...

    if __name__ == "__main__":
        app.run()

The class implements the ASGI protocol (``__call__``) by delegating
to its underlying :class:`fastapi.FastAPI`, so it deploys cleanly
under any ASGI server :

    gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 4
    uvicorn main:app

"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI

from bretzel.runtime import PUBLIC_ASSET_ROUTES
from bretzel.server.config import BretzelConfig
from bretzel.server.decorators.identity import MARK_DOOR, MARK_SOURCE
from bretzel.server.decorators.lifecycle import (
    shutdown as _shutdown_decorator,
)
from bretzel.server.decorators.lifecycle import (
    startup as _startup_decorator,
)
from bretzel.server.decorators.middleware import (
    middleware as _middleware_decorator,
)
from bretzel.server.feature import Feature, validate_features
from bretzel.server.lifecycle import (
    bretzel_shutdown,
    bretzel_startup,
    build_middleware_stack,
)
from bretzel.server.routing.errors import register_error_handlers
from bretzel.theme import Theme


class Bretzel:
    """The Bretzel application instance.

    Construction populates the resolved :class:`BretzelConfig` and
    wires an internal :class:`FastAPI` (with no Swagger/Redoc, since
    apps written in Bretzel are HTML-first, not API-first).

    The class is the natural ASGI app — pass it directly to gunicorn /
    uvicorn / hypercorn. ``app.run()`` is a convenience wrapper
    around uvicorn for dev / single-process deployments.
    """

    def __init__(
        self,
        *,
        title: str = "Bretzel App",
        description: str | None = None,
        theme: Theme | None = None,
        secret_key: str | None = None,
        redis_url: str | None = None,
        workers: int = 1,
        session_max_age_days: int = 30,
        action_max_age: int | None = None,
        mobile_breakpoint: int = 768,
        nav_progress: bool = True,
        pwa: Any = None,
        lang: str = "en",
        languages: Sequence[str] = (),
        texts: Mapping[str, str] | None = None,
        static_dir: str | None = None,
        favicon: str | bool | None = None,
        cors_origins: list[str] | None = None,
        trusted_hosts: list[str] | None = None,
        security_headers: bool = True,
        csp: bool | Literal["report-only"] = False,
        csp_sources: Mapping[str, Sequence[str]] | None = None,
        mode: Literal["dev", "prod"] | None = None,
        secure_cookies: bool | None = None,
        expose_errors: bool | None = None,
        debug: bool | None = None,
        css: Literal["auto", "build", "browser"] | None = None,
    ) -> None:
        # ── Config ──────────────────────────────────────────────────────
        # ``mode`` is a PRESET: it sets the defaults of ``debug``
        # (diagnostics) and ``expose_errors`` (exposure), and governs the
        # assets / cache axis. Each stays overridable on its own. What
        # ``mode`` NO LONGER decides: cookie security, which follows the
        # transport (cf. ``auth.resolve_cookie_secure``).
        # ``mode=None`` falls back on ``$BRETZEL_MODE`` (default "prod").
        config_kwargs: dict[str, Any] = {
            "title": title,
            "description": description,
            "redis_url": redis_url,
            "workers": workers,
            "session_max_age_days": session_max_age_days,
            "action_max_age": action_max_age,
            "mobile_breakpoint": mobile_breakpoint,
            "nav_progress": nav_progress,
            "pwa": pwa,
            "lang": lang,
            "languages": tuple(languages),
            "texts": texts or {},
            "static_dir": static_dir,
            "favicon": favicon,
            "cors_origins": cors_origins or (),
            "trusted_hosts": trusted_hosts or (),
            "security_headers": security_headers,
            "csp": csp,
            "csp_sources": csp_sources or {},
            "secure_cookies": secure_cookies,
            "expose_errors": expose_errors,
            "debug": debug,
            "css": css,
        }
        if secret_key is not None:
            config_kwargs["secret_key"] = secret_key
        if mode is not None:
            if mode not in ("dev", "prod"):
                raise ValueError(
                    f"Bretzel(mode=...) expects 'dev' or 'prod', got {mode!r}."
                )
            config_kwargs["mode"] = mode
        self.config = BretzelConfig.from_kwargs(**config_kwargs)

        # ── Theme ───────────────────────────────────────────────────────
        # Default to the bundled theme if the user didn't supply one ;
        # consistent with ``Theme()`` returning the framework default.
        self._theme = theme if theme is not None else Theme()
        self._theme_css_content: str = ""  # populated at startup
        # The same CSS, without the ``@source inline(...)`` directive:
        # that is what dev mode inlines into every page (the safelist only
        # serves the production compiler). Cf.
        # ``lifecycle._resolve_theme``.
        self._theme_css_inline: str = ""
        # The effective CSS pipeline, set at startup: True = the browser
        # compiler produces the CSS in the page.
        self._css_browser_fallback: bool = True

        # ── Internal collections (``include`` populates these) ──────────
        # Pages + error handlers are discovered from feature modules via
        # :meth:`include` ; layouts need no registry (resolved by direct
        # reference through ``PageMeta.layout`` + the ``_bz_layout``
        # parent chain).
        self._pages: list[Callable[..., Any]] = []
        #: The ``@download`` functions — a file served over GET, not a
        #: page. A separate list: they go through no render pipeline.
        self._downloads: list[Callable[..., Any]] = []
        self._error_handlers: dict[int, Callable[..., Any]] = {}
        self._features: list[Feature] = []
        # Lint L1, computed at startup: routables mounted outside any
        # Feature → [(label, route)]. Read by the app map.
        self._undeclared: list[tuple[str, str]] = []
        self._user_middlewares: list[Any] = []
        # The identity sources declared with ``@auth.source``, in
        # inclusion order — the signed cookie is tried BEFORE them and
        # does not appear here (cf. ``auth.resolve_identity``).
        self._identity_sources: list[Any] = []
        # The doors declared with ``@auth.door``: ``(door, on_user)``.
        # Mounted at startup, like the pages.
        self._doors: list[tuple[Any, Any]] = []
        self._startup_hooks: list[Callable[..., Any]] = []
        self._shutdown_hooks: list[Callable[..., Any]] = []

        # ── Persistence + readiness ─────────────────────────────────────
        # ``_state_backend`` is wired at startup (memory by default,
        # Redis when ``redis_url`` is set).
        self._state_backend: Any = None
        # ``_sse_broker`` is wired at startup too — MemoryBroker for
        # single-worker, Redis-backed in phase 2 for multi-worker. The
        # broadcast fan-out (``broadcast=[State]`` zones) reads it from here ;
        # tests can swap it on a fresh app to inspect signals.
        self._sse_broker: Any = None
        # ``_idempotency_store`` is wired at startup — in-memory for
        # single-worker, Redis for multi-worker. Only ``@idempotent``
        # handlers touch it (opt-in dedup of same-render double-submits).
        self._idempotency_store: Any = None
        self._is_ready: bool = False

        # Cache-bust token : a process-start identifier used by the
        # render pipeline to append ``?h=<token>`` to runtime.js /
        # theme.css URLs in dev mode. Lets a fresh server process
        # invalidate any stale ``immutable`` entries the browser may
        # have pinned from a previous run.
        import time as _time
        self._cache_bust: str = format(int(_time.time()), "x")

        # ── Underlying FastAPI ──────────────────────────────────────────
        # Lifespan ties our startup / shutdown into ASGI ; docs URLs are
        # disabled because Bretzel apps don't expose a JSON-API surface.
        self.fastapi = FastAPI(
            lifespan=self._lifespan,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        # The Bretzel instance, reachable from any request
        # (``request.app`` returns the FastAPI, not us). That is what lets
        # :func:`auth.user_id` find the derived key again without the
        # caller having to pass it — the user's auth guard middleware is
        # the OUTERMOST, so it has neither a render context nor an
        # already-populated ``request.state``.
        self.fastapi.state.bretzel = self

        # Starlette freezes its stack on the first ASGI call. Building
        # it is deferred to ``__call__`` so the user module can declare
        # its ``@app.middleware`` after building the application.
        self._middleware_stack_built = False

        # Exception handlers have the SAME constraint as middlewares :
        # Starlette's ``ExceptionMiddleware`` snapshots
        # ``app.exception_handlers`` when the stack is built (first
        # request / lifespan startup), so post-startup mutations would
        # be invisible. We register the framework's three handlers
        # here. The dict ``self._error_handlers`` is still empty at
        # this point — the handlers close over ``self`` and read it
        # dynamically per request, so user ``@error_page(code)`` calls
        # done after construction land in time.
        register_error_handlers(self.fastapi, self)

    # ── ASGI protocol ────────────────────────────────────────────────────

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """Delegate to the underlying FastAPI. Lets gunicorn / uvicorn /
        hypercorn treat ``Bretzel`` instances as plain ASGI apps.

        It is also the last useful moment to mount the middleware stack:
        the user module is fully imported (so every ``@app.middleware``
        has run) and Starlette has frozen nothing yet. Doing it in
        ``__init__`` froze it before the decorator could exist — cf. the
        comment there.

        ⚠️ **Vendoring happens BEFORE the stack**, and the order is the
        subject: the content security policy is computed in
        ``build_middleware_stack``, from what the shell will ACTUALLY
        load (``vendor.url_for``). Vendoring afterwards means publishing
        a policy that allows the CDNs while the pages serve local routes
        — two truths for one page.
        """
        if not self._middleware_stack_built:
            self._middleware_stack_built = True
            await self._vendor_third_party()
            build_middleware_stack(self)
        await self.fastapi(scope, receive, send)

    async def _vendor_third_party(self) -> None:
        """In dev, serve the third-party scripts from your own host.

        A Bretzel page loads four scripts that do not come from us (htmx,
        idiomorph, the iconify component, the dev CSS compiler) and
        fetches its glyphs from three Iconify hosts. As long as vendoring
        happened ONLY on explicit command, the CDN fallback was the rule
        for anyone unaware the command exists.

        ⚠️ **Dev only.** In production, going out to the network at
        startup would be a surprise; ``python -m bretzel.render.vendor``
        stays the explicit path, and it is worth even more there
        (measured on 2026-08-27: ``DOMContentLoaded`` from 644 ms to
        110 ms).

        ⚠️ **On the threadpool**, never on the loop: these are four
        network downloads, and a slow proxy would block the worker's
        whole startup. It is principle 7 applied to the framework itself.
        """
        if not self.config.is_dev:
            return
        from bretzel.core import call_without_blocking
        from bretzel.render import ensure_vendored

        try:
            await call_without_blocking(ensure_vendored)
        except Exception as exc:
            # ⚠️ **Deliberately broad, and that is the point.**
            # ``ensure_vendored`` already catches per FILE; what remains
            # is what it raises — a non-writable cache, a full disk, a
            # ``.bretzel/`` belonging to another user. Without this
            # guard, an app refuses to start because a CONVENIENCE cache
            # is missing, when the CDN fallback would make it run. Found
            # by ``test_a_failure_never_stops_the_app`` before anyone
            # saw it.
            print(
                f"[bretzel] vendoring impossible ({exc}) — the pages "
                f"will load their scripts from their CDNs"
            )

    # ── Public properties ────────────────────────────────────────────────

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def state_backend(self) -> Any:
        return self._state_backend

    @property
    def sse_broker(self) -> Any:
        """The SSE broker wired at startup, or ``None`` before lifespan.

        Single read-only accessor — render-layer code and the routing
        slabs reach the broker via this property instead of touching
        ``_sse_broker`` directly so the storage shape can evolve
        (Sprint 2 Redis backend, future LRU cache) without rippling
        through every call site.
        """
        return self._sse_broker

    @property
    def idempotency_store(self) -> Any:
        """The ``@idempotent`` dedup store wired at startup, or ``None``
        before lifespan. Read by the action dispatcher."""
        return self._idempotency_store

    @property
    def debug(self) -> bool:
        """The DIAGNOSTICS axis — should the framework be talkative.

        ``debug`` takes the mode as its DEFAULT but can be set on its own
        (``mode="prod", debug=True`` gives a talkative production without
        exposing errors). Read by ``each()`` for the unstable-key warning
        and by the features' AST drift; neither the transport, nor the
        exposure, nor the assets depend on it.
        """
        return self.config.debug

    @property
    def mode(self) -> Literal["dev", "prod"]:
        return self.config.mode

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    # ── Discovery — register pages / error handlers from features ────────

    def include(self, *targets: Any) -> None:
        """Discover and register marked pages / error handlers.

        Each argument is one of :

        - a **module** (or its dotted name string) — every top-level
          callable is scanned for the marks left by the free decorators
          :func:`bretzel.page` / :func:`bretzel.error_page` ;
        - a **marked callable** — a single ``@page`` / ``@error_page``
          function, registered directly ;
        - an **iterable** of the above (e.g. a ``PAGES`` list a
          ``routes`` module builds, including dynamically-generated
          pages that can't be bound to module names).

        Layouts need no registration — a page references its layout
        directly via ``PageMeta.layout`` and the pipeline walks the
        ``parent=`` chain through ``_bz_layout``.

        This is the Bretzel analogue of FastAPI's ``include_router`` /
        Flask's ``register_blueprint`` : features stay app-free (they
        import only ``bretzel``), and the composition root rakes their
        declarations in once ::

            from bretzel import Bretzel
            from myapp.app import routes
            from myapp.infra import errors

            app = Bretzel(secret_key=...)
            app.include(routes.PAGES, errors)

        Idempotent : a page already registered (by identity) is skipped,
        so re-including won't double-mount. Must run before startup (the
        route table is frozen once the ASGI lifespan fires).
        """
        import sys as _sys
        from collections.abc import Iterable
        from types import ModuleType

        for target in targets:
            if isinstance(target, str):
                resolved = _sys.modules.get(target)
                if resolved is None:
                    raise ValueError(
                        f"app.include() can't resolve module {target!r} — it "
                        "isn't imported. Import it first, or pass the module "
                        "object instead of its name."
                    )
                target = resolved
            if isinstance(target, Feature):
                self._register_feature(target)
            elif isinstance(target, ModuleType):
                for value in vars(target).values():
                    if isinstance(value, Feature):
                        self._register_feature(value)
                    else:
                        self._register_declaration(value)
            elif callable(target):
                self._register_declaration(target)
            elif isinstance(target, Iterable):
                for value in target:
                    self.include(value)
            else:
                raise TypeError(
                    "app.include() accepts Feature objects, modules, "
                    "module-name strings, marked callables, or iterables of "
                    f"those — got {target!r}."
                )

    def _register_declaration(self, value: Any) -> None:
        """Register one value if it carries a decoration mark.

        Five marks, and the order of the tests is not indifferent: an
        error handler ALSO carries ``_bz_page``. ``_bz_download`` is
        tested before ``_bz_page`` out of plain symmetry — a function
        never carries both, but the order would be a trap if that
        changed.
        """
        if getattr(value, MARK_SOURCE, False):
            if value not in self._identity_sources:
                self._identity_sources.append(value)
            return
        doors = getattr(value, MARK_DOOR, ())
        if doors:
            known = [d for d, _ in self._doors]
            for door in doors:
                if door not in known:
                    self._doors.append((door, value))
            return
        # Error handlers carry BOTH ``_bz_error_page`` and ``_bz_page`` (the
        # error decorator stamps a PageMeta for the render pipeline) —
        # check error first so they don't also land on the route table.
        err_meta = getattr(value, "_bz_error_page", None)
        if err_meta is not None:
            self._error_handlers[err_meta.status_code] = value
            return
        if getattr(value, "_bz_download", None) is not None:
            if value not in self._downloads:
                self._downloads.append(value)
            return
        if getattr(value, "_bz_page", None) is not None and value not in self._pages:
            self._pages.append(value)

    def _register_feature(self, feature: Feature) -> None:
        """Collect a feature's contract and register the routable items in
        its ``provides`` (pages / error handlers). The full set is
        graph-validated at startup by :func:`validate_features`, so a
        broken contract stops the app assembling rather than half-mounting.
        Deduped by identity, so re-including the same feature is a no-op."""
        if not any(existing is feature for existing in self._features):
            self._features.append(feature)
        for item in feature.provides:
            self._register_declaration(item)

    @property
    def identity_sources(self) -> tuple[Any, ...]:
        """The ``@auth.source`` sources, in inclusion order.

        Read by :func:`bretzel.server.auth.resolve_identity` on every
        request, after the signed cookie.
        """
        return tuple(self._identity_sources)

    @property
    def doors(self) -> tuple[tuple[Any, Any], ...]:
        """The ``@auth.door`` doors and their ``on_user`` — ``((door, fn), …)``."""
        return tuple(self._doors)

    @property
    def public_paths(self) -> frozenset[str]:
        """The paths an auth guard must let through **without knowing
        them**.

        Three families, none of them guessable by the app: the runtime's
        assets (``runtime.js``, the two sheets), and the two routes of
        each sign-in door — the one that sends to the provider and the
        one that receives its return. A guard forgetting the second would
        produce a redirect loop whose symptom points at nothing.

        The app adds its own, **including its sign-in form's action
        path** (:func:`bretzel.server.action_path`) — without which the
        "Sign in" button seems dead. Centralising those paths keeps a new
        internal route from making app guards incomplete.
        """
        paths = set(PUBLIC_ASSET_ROUTES)
        for door, _ in self._doors:
            paths.update(door.paths)
        return frozenset(paths)

    @property
    def undeclared_pages(self) -> tuple[tuple[str, str], ...]:
        """Lint L1 (computed at startup): the routables mounted outside
        any ``Feature`` — ``((label, route), ...)``. Empty when the app
        does not use Features, or when everything is declared."""
        return tuple(self._undeclared)

    @property
    def features(self) -> tuple[Feature, ...]:
        """The feature contracts collected via :meth:`include` — the raw
        material the living-skeleton introspection reads (phase 3)."""
        return tuple(self._features)

    @property
    def routables(self) -> tuple[Any, ...]:
        """Everything MOUNTED that answers a request — pages and error
        handlers, in the order ``_lifespan`` confronts them with the
        ``Feature``.

        This property notably lets ``bretzel check --deep`` read the
        mounted surface without touching the private registries.
        """
        return (*self._pages, *self._error_handlers.values())

    # ── Server-side decorators ───────────────────────────────────────────
    #
    # These three decorators stay methods because they need ``self``:
    # they register something ON this app (a middleware stack or
    # lifecycle hooks).

    def middleware(self, target: Callable[..., Any] | type) -> Callable[..., Any] | type:
        return _middleware_decorator(self, target)

    def startup(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        return _startup_decorator(self, fn)

    def shutdown(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        return _shutdown_decorator(self, fn)

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        *,
        log_level: str = "info",
        reload: bool = False,
        target: str | None = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Start uvicorn embedded — dev and single-process deploys.

        Decoupled from ``Bretzel(mode=...)`` : pass ``reload=True``
        explicitly to get hot-reload, it's not implied by debug. Reload
        requires uvicorn an import string instead of the instance ; we
        introspect ``__main__`` to build one. Override with ``target=``
        when the introspection can't see the instance (factory patterns).

        For production, hand the Bretzel instance to gunicorn / uvicorn
        directly — ``run()`` is for dev convenience only.
        """
        import uvicorn

        if not reload:
            # No reload : passing the instance works (single shared
            # interpreter, full prod path).
            uvicorn.run(
                self,
                host=host,
                port=port,
                workers=self.config.workers,
                reload=False,
                log_level=log_level,
                **uvicorn_kwargs,
            )
            return

        # reload=True : delegate to the Bretzel-owned watcher
        # (``bretzel/server/_dev.py``). uvicorn's own ``--reload`` is
        # broken on Windows — its WatchFiles wrapper detects changes
        # but never kills the worker subprocess. Cf.
        # ``.claude/work/todo.md``.
        if uvicorn_kwargs:
            raise TypeError(
                "app.run(reload=True) does not forward arbitrary "
                "kwargs to the watcher. For custom watch dirs / debounce "
                "/ filters, bypass app.run() and call "
                "``watchfiles.run_process`` directly with "
                "``bretzel.server._dev._run_uvicorn`` as the target. "
                f"Unexpected kwargs : {sorted(uvicorn_kwargs)}"
            )

        if target is None:
            target, app_dir = self._derive_uvicorn_target()
        else:
            # Explicit target = caller owns module resolution ; no
            # app_dir to derive, fall back to __main__ in the watcher.
            app_dir = None

        watch_dirs = self._derive_watch_dirs(app_dir)

        from bretzel.server._dev import run_dev_server

        run_dev_server(
            target=target,
            host=host,
            port=port,
            log_level=log_level,
            watch_dirs=watch_dirs,
        )

    def _derive_uvicorn_target(self) -> tuple[str, str | None]:
        """Find the ``module:varname`` string pointing at ``self``.

        Returns ``(target, app_dir)``. Prefers ``__main__.__spec__.name``
        (``py -m pkg.main``) and falls back to the file's basename
        (``py main.py``, in which case ``app_dir`` is the file's dir so
        uvicorn's worker can re-import by short name).
        """
        import os
        import sys

        main_module = sys.modules.get("__main__")
        if main_module is None:
            raise RuntimeError(
                "app.run() couldn't see __main__. This usually means "
                "you're calling it from an unusual entry point ; pass "
                "``target='module:varname'`` explicitly."
            )

        # Module path : prefer __spec__.name (set when launched via -m),
        # fall back to the file's basename otherwise.
        spec = getattr(main_module, "__spec__", None)
        if spec is not None and spec.name:
            module_path = spec.name
            app_dir: str | None = None
        else:
            file_path = getattr(main_module, "__file__", None)
            if not file_path:
                raise RuntimeError(
                    "app.run() needs the calling script to have either a "
                    "module spec (launched via ``py -m pkg.main``) or a "
                    "__file__ (launched via ``py main.py``)."
                )
            main_path = os.path.abspath(file_path)
            module_path = os.path.splitext(os.path.basename(main_path))[0]
            app_dir = os.path.dirname(main_path)

        var_name: str | None = None
        for name, value in vars(main_module).items():
            if value is self:
                var_name = name
                break
        if var_name is None:
            raise RuntimeError(
                "app.run(reload=True) couldn't find this Bretzel instance "
                "in the calling script's globals. Assign it to a module-"
                "level name (``app = Bretzel(...)``) before calling "
                ".run(), or pass ``target='module:varname'`` explicitly."
            )

        return f"{module_path}:{var_name}", app_dir

    def _derive_watch_dirs(self, app_dir: str | None) -> list:
        """Auto-detect the dirs the dev watcher should monitor.

        - Always : the user app's dir (``app_dir`` if provided, else
          the parent of ``__main__.__file__``).
        - If ``bretzel/`` itself is a local checkout (not under any
          ``site-packages``) : append it so framework dev gets
          auto-reload on framework edits.
        - If ``bretzel/`` lives in ``site-packages`` : skip — those
          files aren't supposed to mutate at runtime.
        """
        import sys
        from pathlib import Path

        import bretzel

        dirs: list[Path] = []

        if app_dir:
            dirs.append(Path(app_dir).resolve())
        else:
            main_module = sys.modules.get("__main__")
            main_file = getattr(main_module, "__file__", None) if main_module else None
            if main_file:
                dirs.append(Path(main_file).resolve().parent)

        bretzel_dir = Path(bretzel.__file__).resolve().parent
        if "site-packages" not in str(bretzel_dir).replace("\\", "/"):
            if bretzel_dir not in dirs:
                dirs.append(bretzel_dir)

        return dirs

    # ── Lifespan — wires our startup / shutdown into FastAPI's ───────────

    @asynccontextmanager
    async def _lifespan(self, _fastapi: FastAPI):  # type: ignore[no-untyped-def]
        # Load-bearing : a lying contract (unknown dep, cycle, name clash)
        # stops the app assembling here, loudly — it never half-starts.
        validate_features(self._features)
        # Soft lints (WARN, never blocking) — the manifest arbitrated
        # against reality. Only when the app opted into Features: an app
        # with no contract has no business being lectured.
        if self._features:
            from bretzel.server.feature import dependency_drift, undeclared_provides

            registered = [*self._pages, *self._error_handlers.values()]
            self._undeclared = undeclared_provides(self._features, registered)
            for label, route in self._undeclared:
                print(f"[bretzel] WARNING: {label!r} ({route or 'no route'}) "
                      "is mounted but not declared by any Feature — it is "
                      "missing from the app map and cannot be validated.")
            if self.config.debug:   # mode="dev" — le drift AST reste hors prod
                for d in dependency_drift(self._features):
                    if d.missing:
                        print(f"[bretzel] WARNING: feature {d.feature!r} "
                              f"imports {list(d.missing)} without declaring "
                              "them in uses/reads.")
                    if d.stale:
                        print(f"[bretzel] WARNING: feature {d.feature!r} "
                              f"declares {list(d.stale)} but never imports them.")
        await bretzel_startup(self)
        try:
            yield
        finally:
            await bretzel_shutdown(self)
