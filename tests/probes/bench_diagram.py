"""Bench app pour le probe de ``ui.diagram`` (port 8999).

Quatre zones, chacune pour une question qu'aucune lecture de HTML ne
peut trancher :

  ``#place``    le graphe de reference — les boites sont-elles bien la
                ou le moteur dit qu'elles sont, une fois le CSS applique ?
  ``#clic``     un graphe cliquable — le calque d'aretes recouvre les
                noeuds, donc c'est la SEULE facon de verifier qu'il
                n'avale pas le clic.
  ``#etroit``   le meme graphe dans un cadre de 320 px — un diagramme
                plus large que sa boite doit DEFILER, pas retrecir.
  ``#colonne``  le graphe dans une colonne flex remplie : le piege du
                `overflow-auto` (hauteur minimale automatique a zero),
                celui que `traps.md` nomme.

Tier-1 user code only. Run :  py tests/probes/bench_diagram.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-diagram-bench-secret-key",
    title="Bretzel - diagram bench",
    mode="dev",
)

# Un losange plus une arete longue : la forme minimale qui exige des
# noeuds fantomes, donc celle ou une arete peut passer SUR un noeud.
EDGES = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("a", "d")]

NODES = [
    ui.node("a", label="alpha", icon="circle"),
    ui.node("b", label="beta", icon="square"),
    ui.node("c", label="gamma", icon="triangle"),
    ui.node("d", label="delta", icon="diamond", badge="3"),
]


def clicked(key: str) -> None:
    """Le handler du probe : il ecrit dans le titre, que le probe relit."""
    ui.notification(f"clic:{key}")


@page("/", title="Diagram bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        with ui.vstack(id="place"):
            ui.diagram(nodes=NODES, edges=EDGES)

        with ui.vstack(id="clic"):
            ui.diagram(nodes=NODES, edges=EDGES, on_item_click=clicked)

        # Plus etroit que le dessin : il doit defiler, pas ecraser.
        with ui.vstack(id="etroit", classes="w-[320px]"):
            ui.diagram(nodes=NODES, edges=EDGES)

        # Le piege de la colonne : une hauteur bornee, un contenu qui
        # deborde, et un enfant qui clippe sa racine.
        with ui.vstack(id="colonne",
                       classes="h-[240px] w-[520px] flex"):
            ui.diagram(nodes=NODES, edges=EDGES, size="xl")


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8999))
