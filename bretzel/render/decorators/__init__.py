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
    refresh,
    refreshable,
    state_qualname,
    zone_ids_watching,
)

__all__ = [
    "DownloadMeta",
    "download",
    "ErrorMeta",
    "LayoutMeta",
    "PageMeta",
    "RefreshableHandle",
    "error_page",
    "layout",
    "page",
    "refresh",
    "refreshable",
    "zone_ids_watching",
    "state_qualname",
]
