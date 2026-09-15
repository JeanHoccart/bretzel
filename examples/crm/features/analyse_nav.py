"""features/analyse_nav — layout : la sous-nav « Analyse » (outlet).

Feature ``kind="layout"`` : une région de rendu qui s'insère ENTRE la
coque et des pages. La chaîne devient ``shell ▸ analyse_nav ▸ {pipeline,
rapports}``, et c'est ce qui fait descendre dans la carte d'app tout ce
qui n'est utilisé que par cette branche — ``reports_data`` cesse d'être
un voisin global pour devenir une feuille sous ``analyse_nav``.

C'est la seule des trois reprises de `mad` qui se voit à l'écran, et
c'est voulu : un ``layout`` qui ne rendrait rien ne démontrerait pas
l'``ui.outlet()``, donc ne vaudrait pas sa déclaration.

Reprise de la sous-nav de l'app `mad` le 2026-09-10, quand elle a été
retirée. Couverture gatée par
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
            ui.link("Rapports", href="/rapports")
        ui.divider()
        ui.outlet()


feature = Feature(name="analyse_nav", kind="layout", provides=[analyse_nav],
                  uses=["shell"])
