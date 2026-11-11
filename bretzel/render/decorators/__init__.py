"""Render-layer decorators (``@page``, ``@layout``, …).

Internal aggregator — the user-facing surface lives on the
:class:`Bretzel` instance, which dispatches ``app.page(...)`` /
``app.layout(...)`` to these implementations.
"""

from bretzel.render.decorators.download import DownloadMeta, download
from bretzel.render.decorators.error import ErrorMeta, error_page
from bretzel.render.decorators.layout import LayoutMeta, layout
from bretzel.render.decorators.page import PageMeta, page
from bretzel.render.decorators.refreshable import (
    RefreshableHandle,
    ZoneRegistry,
    refresh,
    refreshable,
    state_qualname,
    zones_reachable_from,
)

__all__ = [
    "DownloadMeta",
    "download",
    "ErrorMeta",
    "LayoutMeta",
    "PageMeta",
    "RefreshableHandle",
    "ZoneRegistry",
    "zones_reachable_from",
    "error_page",
    "layout",
    "page",
    "refresh",
    "refreshable",
    "state_qualname",
]
