"""features/analyse_nav — layout: the "Analyse" sub-nav (outlet).

A ``kind="layout"`` feature: a render region inserted BETWEEN the shell
and some pages. The chain becomes ``shell ▸ analyse_nav ▸ {pipeline,
rapports}``, and that is what pushes down in the app map everything used
only by this branch — ``reports_data`` stops being a global neighbour and
becomes a leaf under ``analyse_nav``.

It is the only one of `mad`'s three takeovers that shows on screen, and
that is intended: a ``layout`` rendering nothing would not demonstrate
the ``ui.outlet()``, hence would not be worth its declaration.

Taken over from the `mad` app's sub-nav on 2026-09-10, when it was
removed. Coverage gated by
``tests/consistency/test_every_feature_kind_is_exercised.py``.
"""

from __future__ import annotations

from bretzel import Feature, layout, ui
from examples.crm.features.shell import shell


@layout(parent=shell)
def analyse_nav() -> None:
    with ui.vstack(gap="md", classes="w-full min-h-0 flex-1"):
        with ui.hstack(gap="lg", align="center"):
            ui.link("Pipeline", href="/")
            ui.link("Reports", href="/reports")
        ui.divider()
        ui.outlet()


feature = Feature(name="analyse_nav", kind="layout", provides=[analyse_nav],
                  uses=["shell"])
