"""Bench : la barre de progression de NAVIGATION (:8987).

Trois questions, et il faut les trois parce que le depot navigue de
deux facons differentes :

- **lien boost** — un ``ui.link`` interne, boost par le ``hx-boost``
  que le shell pose au niveau document. htmx annonce ``detail.boosted``.
- **item de sidebar** — PAS boost : un ``hx-get`` explicite portant
  ``hx-push-url``. Tester l'un sans l'autre laisserait la moitie des
  menus sans barre.
- **page rapide** — la barre ne doit jamais apparaitre, meme raison que
  pour ``ui.pending()`` : sous le seuil, un temoin fait paraitre
  l'interface plus lente qu'en ne montrant rien.

La page lente dort 700 ms ; la rapide rend tout de suite.

Run :  py tests/probes/bench_nav_progress.py
"""

from __future__ import annotations

import asyncio

from bretzel import Bretzel, layout, page, ui

app = Bretzel(
    secret_key="dev-nav-progress-bench-secret-key",
    title="Bretzel - nav progress bench",
    mode="dev",
)


def shell() -> None:
    with ui.hstack(gap="none", align="stretch", classes="fixed inset-0 w-full"):
        with ui.sidebar(collapsible="rail"):
            with ui.sidebar_section(label="PAGES"):
                ui.sidebar_item("Accueil", href="/", icon="home")
                ui.sidebar_item("Lente", href="/lente", icon="clock")
                ui.sidebar_item("Rapide", href="/rapide", icon="zap")
        with ui.vstack(gap="none", classes="flex-1 min-h-0 overflow-y-auto"):
            ui.outlet()


shell = layout(shell)


@page("/", layout=shell)
def home() -> None:
    with ui.vstack(classes="p-8", gap="md"):
        ui.heading("Accueil", level=1)
        ui.link("Vers la lente (lien boost)", href="/lente",
                attrs={"data-probe": "lien-lent"})
        ui.link("Vers la rapide (lien boost)", href="/rapide",
                attrs={"data-probe": "lien-rapide"})


@page("/lente", layout=shell)
async def lente() -> None:
    await asyncio.sleep(0.7)
    with ui.vstack(classes="p-8"):
        ui.heading("Lente", level=1)
        ui.link("Retour", href="/", attrs={"data-probe": "retour"})


@page("/rapide", layout=shell)
def rapide() -> None:
    with ui.vstack(classes="p-8"):
        ui.heading("Rapide", level=1)
        ui.link("Retour", href="/", attrs={"data-probe": "retour"})


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8987))
