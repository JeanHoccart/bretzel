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
    """Échouer VITE si le backend d'état n'est pas joignable.

    Le contrat ``StateBackend.health()`` annonçait « Called once at app
    startup » depuis toujours — sans aucun appelant (vérifié 2026-08-01). Une
    URL Redis fausse produisait donc une erreur obscure à la PREMIÈRE requête
    utilisateur, au lieu d'un refus de démarrage lisible.

    On ne lève PAS sur un backend qui répond ``False`` sans exception : un
    ``health`` négatif peut être transitoire (Redis qui redémarre), et faire
    tomber le process sur ça rendrait le boot plus fragile que le runtime. On
    lève sur une **exception** — URL invalide, DNS mort, refus de connexion —
    parce que celle-là ne se répare pas toute seule.
    """
    backend = getattr(app, "_state_backend", None)

    # Le protocole est STRUCTUREL : rien à la définition n'oblige une
    # implémentation à être complète, et le manque ne se manifeste qu'à
    # l'appel — pour ``merge``, au commit de fin de requête, c'est-à-dire
    # en production. ``Backend`` est ``runtime_checkable``, donc la
    # vérification coûte une ligne et transforme un plantage en refus de
    # démarrage. Elle ne mord que sur un backend TIERS : les deux du
    # dépôt la passent par construction.
    if backend is not None and not isinstance(backend, Backend):
        manque = sorted(
            nom
            for nom in vars(Backend)
            if not nom.startswith("_") and not hasattr(backend, nom)
        )
        raise RuntimeError(
            f"Le backend d'état ({type(backend).__name__}) n'implémente pas "
            f"tout le protocole Backend : il manque {manque}. Sans ce "
            f"contrôle, l'absence n'aurait levé qu'au premier appel — pour "
            f"``merge``, à la fin de la première requête qui écrit un état."
        )

    check = getattr(backend, "health", None)
    if not callable(check):
        return
    try:
        ok = await check()
    except Exception as exc:  # on re-lève enrichi juste après
        raise RuntimeError(
            f"Le backend d'état ({type(backend).__name__}) est injoignable au "
            f"démarrage : {exc!r}. Vérifie l'URL / les identifiants passés à "
            f"`Bretzel(...)`. (Sans ce contrôle, l'erreur ne serait apparue "
            f"qu'à la première requête.)"
        ) from exc
    if not ok:
        _log.warning(
            "Le backend d'état (%s) répond health()=False au démarrage — "
            "l'app démarre quand même (ça peut être transitoire), mais les "
            "états persistés risquent de ne pas survivre.",
            type(backend).__name__,
        )


async def bretzel_startup(app: Bretzel) -> None:
    """Run framework-side startup. Call before user hooks.

    Middleware registration is NOT done here — Starlette fige sa pile dès
    le premier appel ASGI, lifespan compris, donc un hook de startup
    arrive trop tard.

    ⚠️ La conclusion inverse — « donc le constructeur l'appelle » — a été
    écrite ici et appliquée jusqu'au 2026-08-15. Elle figeait la pile
    AVANT que le code utilisateur ait pu tourner, puisqu'on écrit
    ``@app.middleware`` après ``app = Bretzel(...)``. Résultat :
    ``@app.middleware`` était un **no-op complet**. La construction est
    désormais différée à ``Bretzel.__call__``, seul moment où le module
    utilisateur est importé et où Starlette n'a rien figé.
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
    """Refuser une surcharge de thème que rien ne lira — **avant** tout.

    Premier appel du démarrage, et c'est délibéré : ce qui suit compile du
    CSS, ouvre un backend d'état, monte des routes. Échouer après aurait
    coûté ce travail pour rien, et surtout aurait mêlé le message à des
    traces d'initialisation.

    Pourquoi ici et pas dans ``Theme.__init__`` : le vocabulaire est
    dérivé des classes de composants, et la couche ``theme`` n'a pas le
    droit de les importer (contrat ``base-independent-of-app``). Le
    démarrage est le premier endroit où les deux moitiés coexistent —
    exactement comme ``color_shapes`` juste en dessous. Un ``Theme``
    construit seul (un test, un script) reste donc valide sans la couche
    composants : c'est ce qui le garde testable isolément, et c'est le
    prix assumé de l'asymétrie avec ``semantic=``, qui lève, lui, dès la
    construction.

    Imports différés : ``introspect`` est la couche 7 et ne doit pas peser
    sur l'ordre de chargement du serveur (idiome déjà appliqué à
    ``components`` dans ``_resolve_theme``).
    """
    from bretzel.introspect import theme_vocabulary
    from bretzel.introspect.packages import third_party_theme_vocabulary
    from bretzel.theme.slots import validate_component_overrides

    theme = app.theme
    if theme is None:
        return
    # ⚠️ Le vocabulaire est celui du framework **plus** celui des paquets
    # installés. Sans la seconde moitié, une bibliothèque tierce peut
    # publier des slots que l'app qui l'installe ne peut pas surcharger :
    # il lui reste ``classes=`` au point d'appel, répété partout, sans
    # cascade ni cohérence de thème sombre. C'est la différence entre un
    # composant thémé et du HTML copié.
    #
    # L'ordre compte : les tiers écrasent — mais ils ne peuvent PAS
    # entrer en collision, ``third_party_theme_vocabulary`` lève avant.
    vocabulaire = {**theme_vocabulary(), **third_party_theme_vocabulary()}
    validate_component_overrides(theme.get_component_overrides(), vocabulaire)


def _resolve_theme(app: Bretzel) -> None:
    """Generate theme.css once and stash on the app.

    C'est ici qu'on injecte ce que les thèmes composants savent et que le
    scanner Tailwind ne peut pas deviner — gabarits couleur ET tokens des
    props gradués : premier point de la pile autorisé à voir à la fois
    ``theme`` (socle) et ``components`` (applicatif), cf.
    ``bretzel/components/color_shapes.py``.

    Deux variantes sortent d'ici, parce que les deux consommateurs n'ont
    pas les mêmes besoins :

    - ``_theme_css_content`` — avec la safelist. C'est ce que le
      compilateur de prod ingère, et ce que sert ``/_bretzel/theme.css``.
    - ``_theme_css_inline`` — sans la safelist. C'est le bloc
      ``<style type="text/tailwindcss">`` inliné dans CHAQUE page en dev,
      où le compilateur navigateur scanne le DOM et n'a donc aucun besoin
      de la safelist. L'y laisser coûtait 69 Ko par page (66 % du
      document) et autant de règles à générer avant le premier rendu
      stylé.
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
    """Monter ``config.static_dir`` sur ``/static``, si l'app en déclare un.

    ``static_dir`` était accepté dans la signature de ``Bretzel(...)``,
    stocké dans la config, et documenté « mounted at ``/static`` on the
    underlying FastAPI » — sans qu'aucun ``.mount()`` n'existe dans le
    dépôt (vérifié 2026-08-01). Un utilisateur qui le passait recevait
    donc **rien**, en silence : pire qu'un kwarg absent, qui lui aurait
    levé. Câblé plutôt que retiré — servir un favicon ou un logo est une
    batterie qu'on demande au premier jour.

    Un dossier déclaré mais introuvable **lève au démarrage** : c'est une
    faute de frappe de chemin, et elle ne se répare pas toute seule.
    """
    raw = app.config.static_dir
    if not raw:
        return
    directory = Path(raw)
    if not directory.is_dir():
        raise RuntimeError(
            f"`Bretzel(static_dir={raw!r})` ne pointe pas un dossier "
            f"existant (résolu : {directory.resolve()}). Corrige le chemin, "
            f"ou retire l'argument."
        )
    from starlette.staticfiles import StaticFiles

    # ``check_dir=False`` : on vient de le vérifier, avec un message plus
    # utile que celui de Starlette.
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

    # ``css_pipeline`` (et non le mode) décide : ``build`` compile
    # ``style.css`` avec le binaire Tailwind et le sert en ``<link>`` ;
    # ``browser`` laisse le compilateur navigateur faire le travail dans
    # la page. Cf. ``config.css`` pour le compromis.
    style_css = ""
    app._css_browser_fallback = app.config.css_pipeline == "browser"
    if app.config.css_pipeline == "build" and app._theme_css_content:
        from bretzel.theme.build import get_or_build_css
        from bretzel.theme.compiler import CompilerError

        try:
            # En dev, on recompile toujours. Le cache est clé sur
            # l'empreinte du THÈME : une classe Tailwind fraîchement
            # écrite dans le code utilisateur ne le change pas, donc le
            # cache la ferait disparaître du CSS — silencieusement, ce
            # qui est précisément le mode d'échec qu'on chasse. Qui
            # demande ``css="build"`` en dev a déjà accepté de payer la
            # compilation ; autant qu'elle soit juste.
            style_css = get_or_build_css(
                app._theme_css_content, rebuild=app.config.is_dev
            )
        except CompilerError as exc:
            # Le démarrage ne bloque pas, mais on ne sert PAS une page
            # nue : on retombe explicitement sur le compilateur
            # navigateur, en le disant. Un repli silencieux ferait
            # diverger le rendu de la prod sans que personne le sache —
            # c'est exactement comme ça qu'une safelist amputée est
            # passée inaperçue pendant des mois.
            app._css_browser_fallback = True
            print(
                f"[bretzel] WARN : compilation Tailwind impossible — {exc}\n"
                "[bretzel]        repli sur le compilateur navigateur : le "
                "rendu peut différer de la prod.\n"
                "[bretzel]        installe le binaire avec "
                "``pip install 'bretzel[css]'``."
            )

    register_static_routes(
        app.fastapi,
        runtime_js_path=runtime_js_path,
        # ``strip_scan_roots`` : cette route est publique et sert le
        # thème « pour l'inspection ». Les racines de balayage sont des
        # chemins ABSOLUS du serveur — elles n'ont rien à faire dans une
        # réponse HTTP, et le compilateur navigateur n'en fait rien.
        theme_css=strip_scan_roots(app._theme_css_content),
        style_css=style_css,
        # En-têtes de cache = axe assets, pas diagnostics.
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
    """Monte les portes déclarées par ``@auth.door``.

    Ici et pas à ``include()`` pour la même raison que les pages : le
    routeur se lit à chaque requête, mais la pile ASGI se fige au premier
    appel — le startup est le dernier moment où tout le code utilisateur
    a été importé et où rien n'est encore servi.
    """
    for door, on_user in app.doors:
        door.mount(app, on_user)


def build_middleware_stack(app: Bretzel) -> None:
    """Wrap the FastAPI app in framework + user middlewares.

    Inbound flow (outermost → innermost) :

    - User middlewares (registration order, wrapped LIFO so first
      registered ends up outermost).
    - ``GZipMiddleware`` (gzip niveau 6 ; le SSE en est exclu par type).
    - Trusted hosts / CORS — Starlette stock, opt-in via config.
    - ``SessionMiddleware`` (mints / reads ``Bretzel_session``).
    - ``CSRFMiddleware`` (verifies ``X-Bretzel-CSRF`` on non-safe
      methods using the session id Session just populated ;
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
        # ``None`` = le middleware déduit du scheme, par requête.
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

    # Compression — la couche framework la PLUS EXTERNE, donc elle voit
    # le corps final, après que tout le reste ait écrit.
    #
    # Le HTML de Bretzel est répétitif PAR CONSTRUCTION : la même chaîne
    # de classes Tailwind sur chaque instance d'un composant, la même
    # expression ``bz-*`` sur chaque contrôle du même genre. Mesuré sur
    # ``/datatable`` du playground (2026-08-07) : 9 085 attributs
    # ``class`` pour 328 chaînes distinctes, soit 97 % de doublons — et
    # ``class=`` + ``bz-*`` font à eux deux ~80 % des octets d'une page.
    # C'est exactement ce qu'un compresseur mange : 1 334 Ko → 91 Ko.
    #
    # Niveau 6 et non 9 (le défaut de Starlette) : 5,9 ms de CPU pour
    # cette page contre 113 ms pour la rendre, et le 9 ne gagne que 2 Ko
    # de plus. L'échelle est plate au-delà de 6.
    #
    # ⚠️ Le flux SSE ne doit JAMAIS être compressé — ``apply_compression``
    # ne vide son tampon zlib qu'au dernier chunk, et un flux n'en a pas,
    # donc chaque événement resterait retenu indéfiniment, sans erreur ni
    # trace. Starlette 1.3 l'exclut déjà par type de contenu
    # (``DEFAULT_EXCLUDED_CONTENT_TYPES``), ce qui vaut mieux qu'une
    # exclusion par chemin : ça couvre aussi un flux qu'une app
    # exposerait ailleurs. On en DÉPEND, donc on le GATE —
    # ``tests/integration/server/test_compression.py``.
    app.fastapi.add_middleware(GZipMiddleware, compresslevel=6)

    # En-têtes de sécurité — au-dessus de toute la pile framework (donc
    # ajouté APRÈS elle) pour couvrir aussi les réponses que les couches
    # du dessous produisent seules : un 403 CSRF, un 401 auth, une page
    # d'erreur. Sous la compression, qui reste la plus externe.
    #
    # Les en-têtes ennuyeux sont un défaut, la CSP non : cf.
    # :mod:`bretzel.server.security` pour pourquoi la ligne passe là.
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
    # ``reversed`` parce que ``add_middleware`` enregistre innermost-first
    # (le DERNIER ajouté est le plus externe). En parcourant la liste dans
    # l'ordre, le dernier ``@app.middleware`` écrit devenait le plus
    # externe — l'inverse de ce que promet
    # ``decorators/middleware.py`` : « first registered = outermost ».
    # Personne ne l'avait vu parce qu'aucun middleware utilisateur ne
    # tournait du tout avant le 2026-08-15.
    #
    # C'est la promesse qu'on tient, pas le hasard de l'implémentation :
    # c'est la convention d'une liste écrite de haut en bas (le
    # ``MIDDLEWARE`` de Django se lit ainsi), et c'est celle qui rend une
    # garde d'auth écrite en premier réellement couvrante.
    for user_mw in reversed(getattr(app, "_user_middlewares", None) or []):
        if inspect.isclass(user_mw):
            app.fastapi.add_middleware(user_mw)
        else:
            # Callable async dispatch — wrap with BaseHTTPMiddleware.
            from starlette.middleware.base import BaseHTTPMiddleware

            # ``_mw=user_mw`` lie la valeur de CETTE itération. Une
            # closure nue lirait ``user_mw`` à l'appel du dispatch, donc
            # après la fin de la boucle : avec deux middlewares callables,
            # les deux classes appelleraient le DERNIER, et le premier ne
            # tournerait jamais. Silencieux — la requête passe, le
            # middleware manquant ne se signale pas.
            class _UserMw(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next, _mw=user_mw):  # type: ignore[no-untyped-def]
                    return await _mw(request, call_next)

            app.fastapi.add_middleware(_UserMw)


async def _run_user_hooks(app: Bretzel, hooks: list) -> None:
    for hook in hooks:
        try:
            # Délesté si synchrone (cf. ``core/invoke``) : un hook de
            # démarrage qui migre un schéma ou remplit un cache bloque
            # sinon la boucle pendant que uvicorn dit être prêt.
            await call_without_blocking(hook)
        except Exception as exc:  # surface any startup failure
            raise BretzelError(
                f"Lifecycle hook {hook!r} failed : {exc}"
            ) from exc
