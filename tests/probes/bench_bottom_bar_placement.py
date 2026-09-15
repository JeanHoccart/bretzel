"""Bench app for the bottom-bar placement probe (port 8973).

Les DEUX compositions licites d'une barre ``sticky`` dans le modele
« document gele » (``ui.viewport`` + ``ui.pane``). Les deux fautives ne
sont pas ici : elles LEVENT depuis le 2026-08-24, et c'est
``tests/consistency/test_a_sticky_bar_stays_in_the_frozen_frame.py`` qui
les tient.

Ce banc mesure donc le versant POSITIF de la garde — que les
compositions qu'elle laisse passer rendent bien une barre au bas de
l'ecran, et que la region voisine garde sa largeur. Sans lui, une garde
trop large passerait inapercue : elle rougirait sur du code juste, et
personne n'aurait de mesure a lui opposer.

Tier-1 user code only. Run :  py tests/probes/bench_bottom_bar_placement.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-bottom-bar-placement-bench-secret-key",
    title="Bretzel · bottom bar placement bench",
    mode="dev",
)

TABS = (("Home", "home", "/dans-le-pane"),
        ("Search", "search", "/frere-du-pane"),
        ("Profile", "user", "/dans-le-pane"))


def tabs() -> None:
    with ui.bottom_bar(id="bar"):
        for label, icon, href in TABS:
            ui.bottom_bar_item(label, icon=icon, href=href)


def filler() -> None:
    with ui.vstack(gap="md", classes="p-4"):
        for i in range(40):
            ui.text(f"ligne {i} — de quoi faire defiler la region")


@page("/dans-le-pane", title="A — dans le pane")
def dans_le_pane() -> None:
    """La composition d'``examples/crm`` : dernier enfant de la region."""
    with ui.viewport(direction="col"):
        with ui.pane(gap="none", id="region"):
            filler()
            tabs()


@page("/frere-du-pane", title="B — frere du pane")
def frere_du_pane() -> None:
    """Enfant direct du cadre, apres la region. La forme la plus courte."""
    with ui.viewport(direction="col"):
        with ui.pane(gap="none", id="region"):
            filler()
        tabs()


app.include(dans_le_pane, frere_du_pane)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8973))
