"""SUJET — Les graphiques.

Cinq composants, zéro bibliothèque JavaScript. Ils rendent du SVG côté
serveur, ce qui a trois conséquences qu'on ne mesure qu'à l'usage : rien
à charger, le graphique existe dans le HTML de la première réponse, et
il se voit sur une capture ou un PDF sans qu'un script ait tourné.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/charts"

#: Une série minuscule, rendue en vrai sur cette page — la doc se prend
#: elle-même comme démonstration plutôt que de montrer une capture.
#:
#: ⚠️ Des TUPLES, pas des dicts. La première version de ce chapitre
#: annonçait `[{"x": 1, "y": 12}]` : les quatre graphiques ont rendu
#: « No data », et le probe l'a laissé passer parce qu'il comptait des
#: `<svg>` — l'état vide en est un. Vu sur capture, pas autrement.
DEMO = [(1, 12), (2, 19), (3, 14), (4, 23), (5, 21), (6, 28)]

PARTS = [("Direct", 42), ("Recherche", 31), ("Parrainage", 27)]


@page(PATH, layout=shell, title="Graphiques")
def charts_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Graphiques", level=1, size="3xl")
            ui.text(
                "Cinq composants, aucune bibliothèque JavaScript. Le SVG "
                "est produit par le serveur, donc il est déjà là au "
                "premier octet — rien à charger, rien à attendre.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les cinq", level=2)
                    ui.table(
                        columns=[
                            ui.column("nom", label="Composant"),
                            ui.column("pour", label="Ce qu'il montre"),
                        ],
                        rows=[
                            {"nom": "ui.line_chart",
                             "pour": "une évolution continue, avec "
                                     "réticule au survol"},
                            {"nom": "ui.bar_chart",
                             "pour": "une comparaison entre catégories"},
                            {"nom": "ui.pie_chart",
                             "pour": "une répartition — des parts d'un "
                                     "tout"},
                            {"nom": "ui.scatter_chart",
                             "pour": "une corrélation entre deux "
                                     "grandeurs"},
                            {"nom": "ui.sparkline",
                             "pour": "une tendance MINUSCULE, dans une "
                                     "ligne de texte ou une cellule"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Rendus ici, pour de vrai", level=2)
                    ui.text(
                        "Ce qui suit n'est pas une capture : ce sont les "
                        "composants, exécutés par cette page.",
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ui.line_chart", size="xs",
                                    classes="font-mono", color="muted")
                            ui.line_chart(DEMO, area_fill=True, smooth=True)
                        with ui.vstack(gap="xs"):
                            ui.text("ui.bar_chart", size="xs",
                                    classes="font-mono", color="muted")
                            ui.bar_chart(DEMO)
                        with ui.vstack(gap="xs"):
                            ui.text("ui.pie_chart", size="xs",
                                    classes="font-mono", color="muted")
                            ui.pie_chart(PARTS)
                        with ui.vstack(gap="xs"):
                            ui.text("ui.sparkline — dans une phrase",
                                    size="xs", classes="font-mono",
                                    color="muted")
                            with ui.hstack(gap="sm", align="center"):
                                ui.text("Chiffre d'affaires", size="sm")
                                ui.sparkline(DEMO, area_fill=True)
                                ui.badge("+18 %", color="success",
                                         variant="soft", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La forme des données", level=2)
                    ui.text(
                        "Une liste de TUPLES à deux valeurs. Un couple "
                        "`(x, y)` pour ce qui a deux axes, un couple "
                        "`(libellé, valeur)` pour une répartition.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "ui.line_chart([(1, 12), (2, 19), (3, 14)])\n"
                        "\n"
                        "ui.bar_chart([(\"Jan\", 12), (\"Fév\", 18)])\n"
                        "\n"
                        "ui.pie_chart([(\"Direct\", 42), (\"Recherche\", 31)])\n"
                        "\n"
                        "# Plusieurs séries : une `Series` par courbe.\n"
                        "from bretzel.components import Series\n"
                        "ui.line_chart([Series(name=\"2025\", data=A),\n"
                        "               Series(name=\"2026\", data=B)],\n"
                        "              show_legend=True)\n",
                        lang="python",
                    )
                    ui.alert(
                        "Une mauvaise forme ne LÈVE pas : le graphique "
                        "rend « No data » et la page a l'air normale. "
                        "C'est arrivé en écrivant ce chapitre — les "
                        "quatre exemples ci-dessus étaient vides, et "
                        "seule une capture l'a montré. Le probe, lui, "
                        "comptait des `<svg>` : l'état vide en est un.",
                        color="warning",
                        title="Le mode d'échec à connaître",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les réglages qui servent vraiment", level=2)
                    ui.table(
                        columns=[
                            ui.column("param", label="Paramètre"),
                            ui.column("quoi", label="Ce que ça change"),
                        ],
                        rows=[
                            {"param": "smooth=True",
                             "quoi": "la courbe passe en Bézier au lieu "
                                     "de segments droits"},
                            {"param": "area_fill=True",
                             "quoi": "remplit sous la courbe — lisible "
                                     "pour un volume, trompeur pour une "
                                     "moyenne"},
                            {"param": "show_axis / show_gridlines",
                             "quoi": "à couper pour un graphique "
                                     "d'ambiance, à garder dès qu'on lit "
                                     "des valeurs"},
                            {"param": "y_format / y_unit",
                             "quoi": "formate l'axe — pourcentage, "
                                     "devise, unité"},
                            {"param": "reference_lines",
                             "quoi": "un seuil, un objectif : la ligne "
                                     "qui donne son sens au reste"},
                        ],
                        size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que ça ne fait pas", level=2)
                    ui.text(
                        "Pas de zoom, pas de sélection à la souris, pas "
                        "de courbe qu'on déplace. Ce sont des graphiques "
                        "de LECTURE — le survol montre la valeur, et "
                        "c'est tout. Une exploration interactive demande "
                        "une bibliothèque, donc une dépendance, donc "
                        "exactement ce que ce framework refuse par "
                        "défaut.",
                        color="muted", size="sm",
                    )
