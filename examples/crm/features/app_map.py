"""Feature ``app_map`` — the CRM app's map.

All the rendering lives in the shared renderer
``examples/shared/app_map_view.py``, reused by mad. Here only the
``@page`` providing the CRM's shell is left.

It is the repository's app where the map says most. It quotes no figure:
the previous version announced ten, and the next slice added eight
without the sentence moving — a count copied by hand drifts faster than
it serves, and the page shows it itself, up to date by construction.
"""

from __future__ import annotations

from bretzel import Feature, page
from examples.crm.features.shell import shell
from examples.shared.app_map_view import render_app_map


@page("/_map", layout=shell, title="App map")
def app_map_page() -> None:
    render_app_map()


feature = Feature(name="app_map", kind="page", provides=[app_map_page])
