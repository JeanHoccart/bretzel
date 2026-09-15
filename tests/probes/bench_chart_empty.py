"""Bench — l'état vide des quatre graphiques (port 8981).

Les quatre `ui.*_chart` composent le même `ui.empty_state` depuis le
2026-09-07 (audit § 1.3 : ils n'offraient que `empty_text` quand table,
datatable et diagram offraient les quatre props). Ce bench monte les
trois formes côte à côte — auto, avec description, échappatoire — pour
que `probe_chart_empty.py` mesure ce que le navigateur en fait.

Run :  py tests/probes/bench_chart_empty.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(secret_key="e" * 32, title="Bretzel · chart vide", mode="dev")

#: Les quatre, avec l'icône que chacun pose par défaut.
CHARTS = ("bar_chart", "line_chart", "pie_chart", "scatter_chart")


@page("/")
def vide() -> None:
    """Les trois formes d'état vide, pour les quatre graphiques.

    Un `ui.vstack` et pas un `ui.viewport` : le sujet est la HAUTEUR que
    prend la boîte vide, et un document gelé la contraindrait — on
    mesurerait alors le conteneur, pas le composant.
    """
    with ui.container(width="lg"), ui.vstack(gap="lg"):
        ui.heading("État vide des graphiques", level=1)
        for nom in CHARTS:
            constructeur = getattr(ui, nom)
            with ui.card(padding="md"), ui.vstack(gap="sm"):
                ui.heading(nom, level=2, size="md")

                ui.text("auto", size="xs", color="muted")
                with ui.vstack(gap="none", id=f"{nom}_auto"):
                    constructeur(data=[])

                ui.text("avec description", size="xs", color="muted")
                with ui.vstack(gap="none", id=f"{nom}_desc"):
                    constructeur(
                        data=[],
                        empty_text="Rien à montrer.",
                        empty_icon="unplug",
                        empty_description="Choisis une autre période.",
                    )

                ui.text("échappatoire empty=", size="xs", color="muted")
                with ui.vstack(gap="none", id=f"{nom}_escape"):
                    constructeur(
                        data=[],
                        empty=lambda: ui.button(
                            "Importer un jeu", icon_left="plus",
                            variant="soft", size="sm",
                        ),
                    )


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8981))
