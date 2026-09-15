"""Framework-served static assets — runtime.js, theme.css.

Three things end up under ``/_bretzel/`` :

- ``runtime.js`` : the shipped JS artefact. Read once at startup.
  Deux fichiers, un seul chemin d'URL : le mode dev sert le bundle
  **lisible**, la prod sert ``runtime.min.js``, sa réduction. Cf.
  :func:`_runtime_bundle_for`.
- ``theme.css`` : generated from :class:`Theme.generate_css` at startup.
- ``style.css`` : the Lightning-CSS-compiled output. For phase 1 we
  serve a tiny placeholder when no compile pipeline is wired ; once
  ``bretzel build`` runs (phase 3), this serves the real bundle.

Cache strategy :

- ``dev=True`` → ``Cache-Control: no-store`` everywhere. We
  iterate fast on runtime.js and theme.css, the browser MUST refetch
  on every reload or it pins a stale bundle for 1 year.
- ``dev=False`` (prod) → ``immutable`` + ``max-age=1y``. The bundle
  is content-stable per release ; cache-busting via the ``?h=<hash>``
  query string the shell injects.

The route registrar gets called once at ``Bretzel`` startup and adds
the three GET routes to the underlying FastAPI instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from starlette.responses import FileResponse, Response

from bretzel.render import (
    ROUTE_VENDOR,
    cached_name,
    downloadable_assets,
    icon_payload,
    vendored_is_available,
    vendored_local_path,
)
from bretzel.runtime.protocol import (
    ROUTE_FAVICON,
    ROUTE_ICONS,
    ROUTE_RUNTIME_JS,
    ROUTE_STYLE_CSS,
    ROUTE_THEME_CSS,
    ROUTE_TOUCH_ICON,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-store"

#: La marque, livrée avec le paquet. Deux fichiers, deux métiers : le SVG
#: est l'icône d'onglet et suit ``prefers-color-scheme`` ; le PNG existe
#: parce qu'iOS ne lit pas le SVG pour son écran d'accueil, et qu'il ne
#: gère pas la transparence — d'où son fond blanc.
#:
#: ⚠️ Ils sont servis depuis le PAQUET INSTALLÉ, pas depuis le dépôt : le
#: chemin se dérive de ce module. Une roue construite sans eux rendrait
#: 404 sur l'icône de chaque page, sans une seule erreur serveur — c'est
#: pourquoi ``tests/consistency/test_a_page_always_declares_its_icon.py``
#: vérifie leur présence sur le disque plutôt que de la supposer.
_MARK_DIR = Path(__file__).resolve().parents[2] / "static"
_FAVICON_FILE = _MARK_DIR / "favicon.svg"
_TOUCH_ICON_FILE = _MARK_DIR / "apple-touch-icon.png"


def _runtime_bundle_for(runtime_js_path: Path, *, dev: bool) -> Path:
    """Le fichier à servir : lisible en dev, réduit en prod.

    Le bundle lisible porte 143 Ko de commentaires — de la prose écrite
    pour qui débogue, qui n'a rien à faire dans le navigateur d'un
    visiteur. Sa réduction pèse 26 Ko gzippés contre 90 (mesuré le
    2026-08-27) et se génère au même ``python -m bretzel.runtime._build``.

    **Le repli est explicite, jamais silencieux.** Un dépôt cloné dont
    le build n'a pas été rejoué n'a pas de ``runtime.min.js`` ; refuser
    de démarrer serait brutal, servir l'autre fichier sans le dire
    laisserait une prod deux fois trop lourde passer inaperçue pour
    toujours. On sert donc le lisible **et on le dit**.
    """
    if dev:
        return runtime_js_path
    minified = runtime_js_path.with_name("runtime.min.js")
    if minified.is_file():
        return minified
    print(
        f"[bretzel] {minified.name} absent — la prod sert le bundle lisible "
        f"({runtime_js_path.stat().st_size // 1024} Ko au lieu de ~95). "
        "Lancer ``python -m bretzel.runtime._build``."
    )
    return runtime_js_path


def register_static_routes(
    fastapi: FastAPI,
    *,
    runtime_js_path: Path,
    theme_css: str,
    style_css: str = "",
    # Axe assets / cache. S'appelait ``debug`` — un nom qui laissait
    # croire que la verbosité gouvernait les en-têtes.
    dev: bool = False,
) -> None:
    """Wire the framework asset routes into ``fastapi``.

    The CSS payloads are passed in as strings rather than file paths
    so the caller (lifecycle.py) can hold them in memory and avoid
    a filesystem read per request.
    """
    if not runtime_js_path.is_file():
        raise FileNotFoundError(
            f"Cannot find runtime.js at {runtime_js_path}. Build it via "
            "``python -m bretzel.runtime._build``."
        )

    cache_header = _NO_CACHE if dev else _IMMUTABLE_CACHE
    bundle_path = _runtime_bundle_for(runtime_js_path, dev=dev)

    @fastapi.get(ROUTE_RUNTIME_JS, include_in_schema=False)
    async def _serve_runtime_js() -> FileResponse:
        return FileResponse(
            bundle_path,
            media_type="application/javascript",
            headers={"Cache-Control": cache_header},
        )

    @fastapi.get(f"{ROUTE_VENDOR}/{{filename}}", include_in_schema=False)
    async def _serve_vendored(filename: str) -> FileResponse:
        """Les scripts tiers rapatriés dans ``.bretzel/vendor/``.

        ``filename`` est confronté à la table des trois assets connus, et
        jamais joint au chemin tel quel : une route qui construit un
        chemin depuis l'URL sert tout le disque à qui écrit ``../``.

        ⚠️ La comparaison porte sur :func:`cached_name`, **le nom à
        empreinte**, parce que c'est celui que ``route_for`` met dans le
        ``<script>``. Comparer au ``filename`` amont a livré trois 404 le
        2026-08-27 : l'app perdait htmx et iconify d'un coup, donc ses
        icônes et son transport, sans une seule erreur serveur — juste
        trois lignes de log qu'il fallait lire.
        """
        for asset in downloadable_assets():
            if cached_name(asset) == filename and vendored_is_available(asset):
                return FileResponse(
                    vendored_local_path(asset),
                    media_type="application/javascript",
                    headers={"Cache-Control": cache_header},
                )
        raise HTTPException(status_code=404)

    @fastapi.get(f"{ROUTE_ICONS}/{{chemin:path}}", include_in_schema=False)
    async def _serve_icons(chemin: str, request: Request) -> Response:
        """Les DONNÉES d'icône, relayées et mises en cache.

        Le composant web iconify interroge trois hôtes tiers pour ses
        glyphes. Cette route se met devant : la première demande sort une
        fois depuis le SERVEUR, les suivantes sortent du cache de projet,
        et le navigateur du visiteur ne parle jamais à Iconify.

        ⚠️ **On RELAIE, on ne modélise pas.** Le corps est rendu tel
        qu'Iconify l'a écrit, quel que soit le point d'accès demandé.
        Modéliser son protocole obligerait à suivre chacun de ses points
        (collections, date de modification, recherche) et à repayer la
        dette à chaque évolution amont.

        Un 404 quand rien ne répond : le composant retombe alors sur ses
        propres hôtes, c'est-à-dire le comportement d'avant cette route.
        Ne jamais faire moins bien que ne rien faire.
        """
        query = request.url.query
        demande = f"/{chemin}" + (f"?{query}" if query else "")
        corps = icon_payload(demande)
        if corps is None:
            raise HTTPException(status_code=404)
        return Response(
            content=corps,
            media_type="application/json",
            headers={"Cache-Control": cache_header},
        )

    @fastapi.get(ROUTE_FAVICON, include_in_schema=False)
    async def _serve_favicon() -> FileResponse:
        """La marque du framework, en SVG.

        Montée MÊME quand l'app pose son propre ``favicon=`` : une route
        d'asset conditionnelle rendrait le classement public/privé
        dépendant de la config, et ``PUBLIC_ASSET_ROUTES`` est justement
        ce qu'une garde d'auth lit sans savoir comment l'app est réglée.
        """
        return FileResponse(
            _FAVICON_FILE,
            media_type="image/svg+xml",
            headers={"Cache-Control": cache_header},
        )

    @fastapi.get(ROUTE_TOUCH_ICON, include_in_schema=False)
    async def _serve_touch_icon() -> FileResponse:
        return FileResponse(
            _TOUCH_ICON_FILE,
            media_type="image/png",
            headers={"Cache-Control": cache_header},
        )

    @fastapi.get(ROUTE_THEME_CSS, include_in_schema=False)
    async def _serve_theme_css() -> Response:
        return Response(
            content=theme_css,
            media_type="text/css",
            headers={"Cache-Control": cache_header},
        )

    @fastapi.get(ROUTE_STYLE_CSS, include_in_schema=False)
    async def _serve_style_css() -> Response:
        return Response(
            content=style_css or _EMPTY_STYLE_CSS,
            media_type="text/css",
            headers={"Cache-Control": cache_header},
        )


_EMPTY_STYLE_CSS = (
    "/* Placeholder. Run ``bretzel build`` (or wire Lightning CSS at "
    "startup) to compile your Tailwind utilities into this file. */\n"
)
