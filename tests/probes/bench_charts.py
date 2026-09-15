"""Bench app for the charts V3 probe (port 8956).

Bar (hover tooltip), multi-series Line (hover + legend toggle), Pie
(hover tooltip), Scatter (le survol rend le point plein).

⚠️ Le scatter est arrivé le 2026-09-01, et son absence avait un
coût : son slot ``dot`` annonçait un « hover-pop effect » qui
n'existait pas — ``transition-opacity`` + ``hover:!opacity-100`` sur
un point dont la translucidité est sur le ``fill``, donc une
transition d'une propriété qui ne bouge jamais. Aucun banc ne
survolait un point, donc rien ne pouvait le dire.

Run :  py tests/probes/bench_charts.py
"""

from __future__ import annotations

import math

from bretzel import Bretzel, page, ui
from bretzel.components.charts.series import Series

app = Bretzel(
    secret_key="dev-charts-bench-secret-key",
    title="Bretzel · Charts V3 bench",
    mode="dev",
)

BARS = [("Jan", 12), ("Feb", 19), ("Mar", 8), ("Apr", 25), ("May", 17)]
PIE = [("Chrome", 64), ("Safari", 19), ("Edge", 12), ("Firefox", 5)]
#: Écartés à la main : le probe survole UN point nommément, et deux
#: points qui se chevauchent lui feraient mesurer celui du dessus.
SCATTER = [(1, 10), (3, 26), (5, 14), (7, 32), (9, 20)]
SERIES = [
    Series(name="Acme", data=[(i, round(60 + 15 * math.sin(i / 1.5), 1)) for i in range(12)]),
    Series(name="Globex", data=[(i, round(45 + 20 * math.cos(i / 1.8), 1)) for i in range(12)]),
]


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Charts V3 bench", size="2xl", weight="bold")

        ui.text("Bar", weight="semibold")
        with ui.container(id="bar-wrap"):
            ui.bar_chart(BARS, width=420)

        ui.text("Line (multi-series + legend)", weight="semibold")
        with ui.container(id="line-wrap"):
            ui.line_chart(SERIES, width=480)

        ui.text("Pie", weight="semibold")
        with ui.container(id="pie-wrap"):
            ui.pie_chart(PIE, size="md")

        ui.text("Scatter (survol = point plein)", weight="semibold")
        with ui.container(id="scatter-wrap"):
            ui.scatter_chart(SCATTER, width=420, size="md")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8956))
