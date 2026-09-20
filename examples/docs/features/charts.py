"""TOPIC — The charts.

Five components, zero JavaScript library. They render SVG on the server,
which has three consequences one only measures in use: nothing to load,
the chart exists in the first response's HTML, and it shows on a
screenshot or a PDF without a script having run.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/charts"

#: A tiny series, rendered for real on this page — the docs take
#: themselves as the demonstration rather than showing a screenshot.
#:
#: ⚠️ TUPLES, not dicts. This chapter's first version announced
#: `[{"x": 1, "y": 12}]`: the four charts rendered "No data", and the
#: probe let it through because it counted `<svg>` — the empty state is
#: one. Seen on a screenshot, not otherwise.
DEMO = [(1, 12), (2, 19), (3, 14), (4, 23), (5, 21), (6, 28)]

PARTS = [("Direct", 42), ("Recherche", 31), ("Parrainage", 27)]


@page(PATH, layout=shell, title="Graphiques")
def charts_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Graphiques", level=1, size="3xl")
            ui.text(
                tr('Five components, no JavaScript library. The SVG is '
                   'produced by the server, so it is already there at the '
                   'first byte — nothing to load, nothing to wait for.',
                   'Cinq composants, aucune bibliothèque JavaScript. Le SVG '
                   'est produit par le serveur, donc il est déjà là au '
                   'premier octet — rien à charger, rien à attendre.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The five',
                                  'Les cinq'), level=2)
                    ui.table(
                        columns=[
                            ui.column("nom", label="Composant"),
                            ui.column(tr('for',
                                         'pour'), label="Ce qu'il montre"),
                        ],
                        rows=[
                            {"nom": "ui.line_chart",
                             tr('for',
                                'pour'): tr('a continuous evolution, with a '
                                        'crosshair on hover',
                                        'une évolution continue, avec '
                                        'réticule au survol')},
                            {"nom": "ui.bar_chart",
                             tr('for',
                                'pour'): tr('a comparison between categories',
                                        'une comparaison entre catégories')},
                            {"nom": "ui.pie_chart",
                             tr('for',
                                'pour'): tr('a breakdown — shares of a whole',
                                        "une répartition — des parts d'un tout")},
                            {"nom": "ui.scatter_chart",
                             tr('for',
                                'pour'): tr('a correlation between two quantities',
                                        'une corrélation entre deux grandeurs')},
                            {"nom": "ui.sparkline",
                             tr('for',
                                'pour'): tr('a TINY trend, inside a line of text '
                                        'or a cell',
                                        'une tendance MINUSCULE, dans une '
                                        'ligne de texte ou une cellule')},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Rendered here, for real',
                                  'Rendus ici, pour de vrai'), level=2)
                    ui.text(
                        tr('What follows is not a screenshot: these are the '
                           'components, executed by this page.',
                           "Ce qui suit n'est pas une capture : ce sont les "
                           'composants, exécutés par cette page.'),
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
                            ui.text(tr('ui.sparkline — inside a sentence',
                                       'ui.sparkline — dans une phrase'),
                                    size="xs", classes="font-mono",
                                    color="muted")
                            with ui.hstack(gap="sm", align="center"):
                                ui.text("Chiffre d'affaires", size="sm")
                                ui.sparkline(DEMO, area_fill=True)
                                ui.badge("+18 %", color="success",
                                         variant="soft", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The shape of the data',
                                  'La forme des données'), level=2)
                    ui.text(
                        tr('A list of two-value TUPLES. An `(x, y)` pair for '
                           'what has two axes, a `(label, value)` pair for a '
                           'breakdown.',
                           'Une liste de TUPLES à deux valeurs. Un couple '
                           '`(x, y)` pour ce qui a deux axes, un couple '
                           '`(libellé, valeur)` pour une répartition.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('ui.line_chart([(1, 12), (2, 19), (3, 14)])\n\nui.bar_chart([("Jan", 12), ("Feb", 18)])\n\nui.pie_chart([("Direct", 42), ("Search", 31)])\n\n# Several series: one `Series` per curve.\nfrom bretzel.components import Series\nui.line_chart([Series(name="2025", data=A),\n               Series(name="2026", data=B)],\n              show_legend=True)\n',
                           'ui.line_chart([(1, 12), (2, 19), (3, 14)])\n\nui.bar_chart([("Jan", 12), ("Fév", 18)])\n\nui.pie_chart([("Direct", 42), ("Recherche", 31)])\n\n# Plusieurs séries : une `Series` par courbe.\nfrom bretzel.components import Series\nui.line_chart([Series(name="2025", data=A),\n               Series(name="2026", data=B)],\n              show_legend=True)\n'),
                        lang="python",
                    )
                    ui.alert(
                        tr('A wrong shape does not RAISE: the chart renders '
                           '“No data” and the page looks normal. It happened '
                           'while writing this chapter — the four examples '
                           'above were empty, and only a screenshot showed '
                           'it. The probe, for its part, was counting '
                           '`<svg>`s: the empty state is one.',
                           'Une mauvaise forme ne LÈVE pas : le graphique '
                           "rend « No data » et la page a l'air normale. "
                           "C'est arrivé en écrivant ce chapitre — les quatre"
                           ' exemples ci-dessus étaient vides, et seule une '
                           "capture l'a montré. Le probe, lui, comptait des "
                           "`<svg>` : l'état vide en est un."),
                        color="warning",
                        title=tr('The failure mode to know about',
                                 "Le mode d'échec à connaître"),
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The settings that really serve',
                                  'Les réglages qui servent vraiment'), level=2)
                    ui.table(
                        columns=[
                            ui.column("param", label=tr('Parameter',
                                                        'Paramètre')),
                            ui.column("quoi", label=tr('What it changes',
                                                       'Ce que ça change')),
                        ],
                        rows=[
                            {"param": "smooth=True",
                             "quoi": tr('the curve goes Bézier instead of '
                                        'straight segments',
                                        'la courbe passe en Bézier au lieu de'
                                        ' segments droits')},
                            {"param": "area_fill=True",
                             "quoi": tr('fills under the curve — readable for'
                                        ' a volume, misleading for an average',
                                        'remplit sous la courbe — lisible '
                                        'pour un volume, trompeur pour une '
                                        'moyenne')},
                            {"param": "show_axis / show_gridlines",
                             "quoi": tr('to turn off for a mood chart, to '
                                        'keep as soon as values get read',
                                        'à couper pour un graphique '
                                        "d'ambiance, à garder dès qu'on lit "
                                        'des valeurs')},
                            {"param": "y_format / y_unit",
                             "quoi": tr('formats the axis — percentage, '
                                        'currency, unit',
                                        "formate l'axe — pourcentage, devise,"
                                        ' unité')},
                            {"param": "reference_lines",
                             "quoi": tr('a threshold, a target: the line that'
                                        ' gives the rest its meaning',
                                        'un seuil, un objectif : la ligne qui'
                                        ' donne son sens au reste')},
                        ],
                        size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What it does not do',
                                  'Ce que ça ne fait pas'), level=2)
                    ui.text(
                        tr('No zoom, no mouse selection, no curve one drags. '
                           'These are READING charts — hovering shows the '
                           'value, and that is all. Interactive exploration '
                           'needs a library, hence a dependency, hence '
                           'exactly what this framework refuses by default.',
                           'Pas de zoom, pas de sélection à la souris, pas de'
                           " courbe qu'on déplace. Ce sont des graphiques de "
                           "LECTURE — le survol montre la valeur, et c'est "
                           'tout. Une exploration interactive demande une '
                           'bibliothèque, donc une dépendance, donc '
                           'exactement ce que ce framework refuse par défaut.'),
                        color="muted", size="sm",
                    )
