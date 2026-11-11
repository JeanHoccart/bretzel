"""TOPIC — The charts.

Five components, zero JavaScript library. They render SVG on the server,
which has three consequences one only measures in use: nothing to load,
the chart exists in the first response's HTML, and it shows on a
screenshot or a PDF without a script having run.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/charts"

#: A tiny series, rendered for real on this page — the docs take
#: themselves as the demonstration rather than showing a screenshot.
#:
#: ⚠️ TUPLES, not dicts. This chapter's first version announced
#: `[{"x": 1, "y": 12}]`: the four charts rendered "No data", and the
#: probe let it through because it counted `<svg>` — the empty state is
#: one. Seen on a screenshot, not otherwise.
DEMO = [(1, 12), (2, 19), (3, 14), (4, 23), (5, 21), (6, 28)]

PARTS = [("Direct", 42), ("Search", 31), ("Referral", 27)]


@page(PATH, layout=shell, title="Charts · Bretzel docs",
      description="Server-rendered SVG charts in Python: five Bretzel chart components with no JavaScript library, visible from the first byte.")
def charts_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Charts", level=1, size="3xl")
            ui.text(
                'Five components, no JavaScript library. The SVG is '
                'produced by the server, so it is already there at the '
                'first byte — nothing to load, nothing to wait for.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The five', level=2)
                    ui.table(
                        columns=[
                            ui.column("nom", label="Component"),
                            ui.column('for', label="What it shows"),
                        ],
                        rows=[
                            {"nom": "ui.line_chart",
                             'for': 'a continuous evolution, with a '
                                     'crosshair on hover'},
                            {"nom": "ui.bar_chart",
                             'for': 'a comparison between categories'},
                            {"nom": "ui.pie_chart",
                             'for': 'a breakdown — shares of a whole'},
                            {"nom": "ui.scatter_chart",
                             'for': 'a correlation between two quantities'},
                            {"nom": "ui.sparkline",
                             'for': 'a TINY trend, inside a line of text '
                                     'or a cell'},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Rendered here, for real', level=2)
                    ui.text(
                        'What follows is not a screenshot: these are the '
                        'components, executed by this page.',
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
                            ui.text('ui.sparkline — inside a sentence',
                                    size="xs", classes="font-mono",
                                    color="muted")
                            with ui.hstack(gap="sm", align="center"):
                                ui.text("Revenue", size="sm")
                                ui.sparkline(DEMO, area_fill=True)
                                ui.badge("+18 %", color="success",
                                         variant="soft", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The shape of the data', level=2)
                    ui.text(
                        'A list of two-value TUPLES. An `(x, y)` pair for '
                        'what has two axes, a `(label, value)` pair for a '
                        'breakdown.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.line_chart([(1, 12), (2, 19), (3, 14)])\n\nui.bar_chart([("Jan", 12), ("Feb", 18)])\n\nui.pie_chart([("Direct", 42), ("Search", 31)])\n\n# Several series: one `Series` per curve.\nfrom bretzel.components import Series\nui.line_chart([Series(name="2025", data=A),\n               Series(name="2026", data=B)],\n              show_legend=True)\n',
                        lang="python",
                    )
                    ui.alert(
                        'A wrong shape does not RAISE: the chart renders '
                        '“No data” and the page looks normal. It happened '
                        'while writing this chapter — the four examples '
                        'above were empty, and only a screenshot showed '
                        'it. The probe, for its part, was counting '
                        '`<svg>`s: the empty state is one.',
                        color="warning",
                        title='The failure mode to know about',
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The settings that really serve', level=2)
                    ui.table(
                        columns=[
                            ui.column("param", label='Parameter'),
                            ui.column("quoi", label='What it changes'),
                        ],
                        rows=[
                            {"param": "smooth=True",
                             "quoi": 'the curve goes Bézier instead of '
                                     'straight segments'},
                            {"param": "area_fill=True",
                             "quoi": 'fills under the curve — readable for'
                                     ' a volume, misleading for an average'},
                            {"param": "show_axis / show_gridlines",
                             "quoi": 'to turn off for a mood chart, to '
                                     'keep as soon as values get read'},
                            {"param": "y_format / y_unit",
                             "quoi": 'formats the axis — percentage, '
                                     'currency, unit'},
                            {"param": "y_reference_lines",
                             "quoi": 'a threshold, a target: the line that'
                                     ' gives the rest its meaning'},
                            {"param": "x_reference_lines",
                             "quoi": 'a moment — a buy, a sale, a release:'
                                     ' a vertical line at its date'},
                            {"param": "None in data=",
                             "quoi": 'a hole: the line stops, never drops to'
                                     ' zero; series may have different dates'},
                        ],
                        size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('What it does not do', level=2)
                    ui.text(
                        'No zoom, no mouse selection, no curve one drags. '
                        'These are READING charts — hovering shows the '
                        'value, and that is all. Interactive exploration '
                        'needs a library, hence a dependency, hence '
                        'exactly what this framework refuses by default.',
                        color="muted", size="sm",
                    )
