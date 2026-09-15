"""Bench : automatic hx-boost partial-nav + bridge URL-clean (:8976).

A minimal shell (sidebar + outlet) with two pages linked by a plain
``ui.link`` content link, plus a ColorScheme toggle (client state). Tests
that clicking an internal link :
  - swaps only the outlet (the sidebar DOM node persists),
  - pushes the URL **without** leaking the client store into the query
    string (the bridge POST-only fix).

Run :  py tests/probes/bench_boost.py
"""

from __future__ import annotations

from bretzel import Bretzel, layout, page, ui
from bretzel.theme import ColorScheme

app = Bretzel(secret_key="dev-boost-bench-secret-key", mode="dev")


def shell() -> None:
    scheme = ColorScheme()
    with ui.hstack(gap="none", align="stretch",
                   classes="fixed inset-0 w-full"):
        with ui.sidebar(collapsible="offcanvas"):
            with ui.sidebar_section(label="PAGES"):
                ui.sidebar_item("Page A", href="/", icon="home")
                ui.sidebar_item("Page B", href="/b", icon="box")
            # ColorScheme toggle → puts ColorScheme.default.mode in the
            # client store (the thing that used to leak into the URL).
            ui.icon_button("moon", variant="ghost", on_click=scheme.toggle())
        with ui.vstack(gap="none", classes="flex-1 min-h-0 overflow-y-auto"):
            # Une barre ``offcanvas`` quitte l'écran en se repliant, donc
            # elle a besoin d'un moyen de revenir — exigé par
            # ``check_sidebars_are_reachable`` depuis a0cbab3f, qui
            # rendait ce bench 500 (et donc ``probe_boost`` rouge).
            ui.sidebar_trigger()
            ui.outlet()


shell = layout(shell)


@page("/", layout=shell)
def page_a() -> None:
    with ui.vstack(classes="p-8"):
        ui.heading("Page A", level=1)
        ui.link("Go to B (plain content link)", href="/b")


@page("/b", layout=shell)
def page_b() -> None:
    with ui.vstack(classes="p-8"):
        ui.heading("Page B", level=1)
        ui.link("Back to A", href="/")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8976))
