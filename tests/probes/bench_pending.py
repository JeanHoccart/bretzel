"""Bench : ``ui.pending()`` — le témoin « une action est en vol » (:8986).

Trois questions, trois zones :

- **slow** — un handler à 700 ms. Le spinner DOIT apparaître, mais pas
  avant le seuil de 200 ms.
- **fast** — un handler à ~10 ms. Le spinner ne doit JAMAIS apparaître :
  c'est tout l'intérêt du seuil, et c'est invisible à l'œil comme à
  ``getComputedStyle`` après coup (cf. la memory sur les instruments
  d'état stable). Le probe échantillonne DANS la page.
- **remote** — un squelette ailleurs dans le DOM, adressé par le
  handler (``ui.pending(slow_save)``), plus un bouton ``after=0`` qui
  doit se désactiver dès le premier clic sans temporisation.

Run :  py tests/probes/bench_pending.py
"""

from __future__ import annotations

import asyncio

import examples.playground.main  # noqa: F401
from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-pending-bench-secret-key",
    title="Bretzel · pending bench",
    mode="dev",
)


async def slow_save() -> None:
    await asyncio.sleep(0.7)


async def fast_save() -> None:
    await asyncio.sleep(0.01)


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-12 min-h-screen bg-background"):
        ui.heading("ui.pending() — témoin d'action en vol", level=2)

        ui.text("slow (700 ms) — le spinner doit venir, après 200 ms",
                color="muted")
        ui.button("Slow", on_click=slow_save, loading=ui.pending(),
                  attrs={"data-probe": "slow"})

        ui.text("fast (10 ms) — le spinner ne doit JAMAIS venir",
                color="muted")
        ui.button("Fast", on_click=fast_save, loading=ui.pending(),
                  attrs={"data-probe": "fast"})

        ui.text("after=0 — désactivation immédiate, sans seuil",
                color="muted")
        ui.button("Immediate", on_click=slow_save,
                  disabled=ui.pending(slow_save, after=0),
                  attrs={"data-probe": "immediate"})

        ui.text("adressage à distance — ce squelette suit slow_save",
                color="muted")
        ui.skeleton(visible=ui.pending(slow_save), variant="rectangle",
                    attrs={"data-probe": "remote"})


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8986))
