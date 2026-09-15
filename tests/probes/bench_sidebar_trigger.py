"""Bench app for the sidebar-trigger probe (port 8976).

Une coque mobile reelle : cadre gele, barre laterale en ``overlay``
fermee au chargement, et le declencheur pose dans la barre du haut de
l'app — la composition que ``ui.sidebar_trigger`` existe pour rendre
ecrivable.

Ce qu'on vient mesurer ici ne se voit qu'au navigateur : que le clic
FAIT REVENIR la barre. Le rendu Python, lui, est tenu par
``tests/unit/components/navigation/test_sidebar_trigger.py``, et la
composition par ``tests/consistency/test_a_sidebar_can_always_come_back.py``.

Tier-1 user code only. Run :  py tests/probes/bench_sidebar_trigger.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-sidebar-trigger-bench-secret-key",
    title="Bretzel · sidebar trigger bench",
    mode="dev",
)

NAV = (("Accueil", "home", "/"), ("Clients", "users", "/"),
       ("Ventes", "trending-up", "/"))


@page("/", title="Sidebar trigger bench")
def home() -> None:
    with ui.viewport(direction="col"):
        with ui.sidebar(collapsible="overlay", open=False, id="sb"):
            ui.sidebar_title("Demo", icon=ui.icon("zap"))
            with ui.sidebar_section(label="NAV"):
                for label, icon, href in NAV:
                    ui.sidebar_item(label, icon=icon, href=href)
        with ui.pane(id="region"):
            with ui.hstack(align="center", gap="sm",
                           classes="px-4 py-2 border-b border-text/10"):
                ui.sidebar_trigger(id="trigger")
                ui.text("Mon app", weight="semibold")
            with ui.vstack(gap="md", classes="p-4"):
                for i in range(12):
                    ui.text(f"ligne {i}")


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8976))
