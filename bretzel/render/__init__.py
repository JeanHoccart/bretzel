"""INTERNAL layer — server-driven HTML rendering implementation."""

from __future__ import annotations

from bretzel.render.context import (
    RenderContext,
    current_context,
    maybe_current_context,
    use_context,
)
from bretzel.render.decorators import (
    DownloadMeta,
    ErrorMeta,
    LayoutMeta,
    PageMeta,
    RefreshableHandle,
    download,
    error_page,
    layout,
    page,
    refresh,
    refreshable,
    state_qualname,
    zone_ids_watching,
)
from bretzel.render.fusion import FusionConflict, fuse_or_wrap
from bretzel.render.iteration import current_iteration_key
from bretzel.render.lang import (
    Language,
    LanguageTables,
    negotiate_language,
    resolve_language,
)
from bretzel.render.partials import (
    RenderResult,
    drain_refresh_queue,
    render_partial,
)
from bretzel.render.pipeline import render_page
from bretzel.render.serialize import serialize_html
from bretzel.render.shell import (
    DEFAULT_HTMX_URL,
    default_shell,
    shell_sources,
)
from bretzel.render.texts import (
    DEFAULT_TEXTS,
    TextsError,
    plural,
    resolve_texts,
    template,
    text,
)
from bretzel.render.types import BretzelApp
from bretzel.render.vendor import (
    ROUTE_ICONS,
    ROUTE_VENDOR,
    VendoredAsset,
    cached_name,
    downloadable_assets,
    ensure_vendored,
    icon_payload,
    vendored_assets,
    vendored_is_available,
    vendored_local_path,
)

__all__ = [
    # Context
    "RenderContext",
    "current_context",
    "maybe_current_context",
    "use_context",
    # Pipeline entry points
    "render_page",
    "render_partial",
    "drain_refresh_queue",
    "RenderResult",
    # Document assembly
    "default_shell",
    "shell_sources",
    "DEFAULT_TEXTS",
    "TextsError",
    "plural",
    "LanguageTables",
    "Language",
    "negotiate_language",
    "resolve_language",
    "resolve_texts",
    "template",
    "text",
    "DEFAULT_HTMX_URL",
    # Scripts tiers rapatriés (``.bretzel/vendor/``) — la couche serveur
    # les sert, elle passe donc par ici et non par le sous-module.
    "ROUTE_ICONS",
    "ROUTE_VENDOR",
    "VendoredAsset",
    "cached_name",
    "downloadable_assets",
    "ensure_vendored",
    "icon_payload",
    "vendored_assets",
    "vendored_is_available",
    "vendored_local_path",
    # Inspection helper
    "serialize_html",
    # No-div-soup fusion
    "fuse_or_wrap",
    "FusionConflict",
    # Keyed iteration key context
    "current_iteration_key",
    # Decorators (internal; re-exported from bretzel)
    "download",
    "page",
    "PageMeta",
    "layout",
    "LayoutMeta",
    "refresh",
    "refreshable",
    "zone_ids_watching",
    "RefreshableHandle",
    "state_qualname",
    "error_page",
    "ErrorMeta",
    # Protocols
    "BretzelApp",
]
